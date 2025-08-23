import sys
import struct
import math

class Drive:
    def __init__(self, f, bps=512):
        self._bps = bps
        self._fd = f

    def read_sectors(self, offset, count=1):
        self._fd.seek(offset * self._bps)
        return self._fd.read(count * self._bps)
    
class EXT:
    def __init__(self, drive):
        self._drive = drive
    
    def parse_superblock(self):
        sb = self._drive.read_sectors(2, 2)
        (total_inodes, total_blocks) = struct.unpack_from("<II", sb, 0x00)
        (log_block_size, _tmp1, blocks_per_group, _tmp2, inodes_per_group) = struct.unpack_from("<IIIII", sb, 0x18)
        inode_structure_size = struct.unpack_from("<H", sb, 0x58)[0]
        gdt_size = struct.unpack_from("<H", sb, 0xFE)[0]
        if gdt_size == 0:
            gdt_size = 32

        self._sb = {
            "total_inodes": total_inodes,
            "total_blocks": total_blocks,
            "inodes_per_group": inodes_per_group,
            "blocks_per_group": blocks_per_group,
            "block_size": (1 << log_block_size) * 1024,
            "inode_structure_size": inode_structure_size,
            "gdt_size": gdt_size,
        }

        self._spc = self._sb["block_size"] // self._drive._bps
        self._block_group_count = self.get_block_groups()

    def read_blocks(self, offset, count=1):
        return self._drive.read_sectors(offset * self._spc, count * self._spc)
    
    def get_block_groups(self):
        gi = math.ceil(self._sb["total_inodes"] / self._sb["inodes_per_group"]) if self._sb["inodes_per_group"] else 0
        gb = math.ceil(self._sb["total_blocks"] / self._sb["blocks_per_group"]) if self._sb["blocks_per_group"] else 0
        return max(gi, gb)
    
    def get_inode(self, n):
        gdt_number = (n-1) // self._sb["inodes_per_group"]
        offset = (n-1) % self._sb["inodes_per_group"]

        inode_block_offset = self._gdts[gdt_number]

        inode_size = self._sb["inode_structure_size"]
        inode_block_count = math.ceil((inode_size * self._sb["inodes_per_group"]) / self._sb["block_size"])
        inodes = self.read_blocks(inode_block_offset, inode_block_count)
        inode = inodes[offset*inode_size:(offset+1) * inode_size]

        return inode

    def _ptrs_per_block(self):
        return self._sb["block_size"] // 4

    def parse_indirect(self, blocks, v):
        data = self.read_blocks(v)
        n = self._ptrs_per_block()
        for i in range(n):
            (v1,) = struct.unpack_from("<I", data, i*4)
            if v1 == 0:
                continue
            blocks.append(v1)

    def parse_double_indirect(self, blocks, v):
        data = self.read_blocks(v)
        n = self._ptrs_per_block()
        for i in range(n):
            (v1,) = struct.unpack_from("<I", data, i*4)
            if v1 == 0:
                continue
            self.parse_indirect(blocks, v1)

    def parse_triple_indirect(self, blocks, v):
        data = self.read_blocks(v)
        n = self._ptrs_per_block()
        for i in range(n):
            (v1,) = struct.unpack_from("<I", data, i*4)
            if v1 == 0:
                continue
            self.parse_double_indirect(blocks, v1)

    def parse_inode(self, inode):
        flags = struct.unpack_from("<I", inode, 0x20)[0]
        if flags & 0x80000 == 0x80000:
            return self.parse_extents(inode)
        else:
            return self.parse_direct_blocks(inode)

    def parse_extents(self, inode):
        """
        요구 조건:
        - ext4의 extents는 i_block(60B) 안에 **leaf** 노드만 존재
        - index node가 나오면 즉시 실패
        """
        i_block = inode[0x28:0x28 + 60]
        eh_magic, eh_entries, eh_max, eh_depth, _ = struct.unpack_from("<HHHHI", i_block, 0)
        if eh_magic != 0xF30A:
            raise Exception("Invalid Extent Header Magic")
        if eh_depth != 0:
            raise NotImplementedError("Non-leaf extent is not supported for this task")
        if eh_entries > 4:
            raise Exception("Extent entries exceed inline 60-byte area")

        blocks = []
        for i in range(eh_entries):
            ee_block, ee_len, ee_start_hi, ee_start_lo = struct.unpack_from("<IHHI", i_block, 12 + i*12)
            length = ee_len & 0x7FFF
            start = (ee_start_hi << 32) | ee_start_lo
            for y in range(length):
                blocks.append(start + y)
        return blocks

    def parse_direct_blocks(self, inode):
        i_block = inode[0x28:0x28 + 60]
        blocks = []
        for i in range(15):
            v = struct.unpack_from("<I", i_block, i*4)[0]
            if v == 0:
                continue
            if i == 12:
                self.parse_indirect(blocks, v)
            elif i == 13:
                self.parse_double_indirect(blocks, v)
            elif i == 14:
                self.parse_triple_indirect(blocks, v)
            else:
                blocks.append(v)
        return blocks

    def load_blocks(self, blocks):
        data = b""
        for b in blocks:
            data += self.read_blocks(b)
        return data
    
    def _inode_i_size(self, inode):
        return struct.unpack_from("<I", inode, 0x04)[0]

    def parse_directory(self, inode):
        blocks = self.parse_inode(inode)
        data = self.load_blocks(blocks)
        max_size = min(len(data), self._inode_i_size(inode))
        offset = 0
        entries = []
        while offset + 8 <= max_size:
            (inode_no, rec_len, name_len, _type) = struct.unpack_from("<IHBB", data, offset)
            if rec_len == 0:
                break
            if inode_no == 0:
                offset += rec_len
                continue
            name_bytes = data[offset + 8:offset + 8 + name_len]
            try:
                name = name_bytes.decode("utf-8")
            except UnicodeDecodeError:
                name = name_bytes.decode("utf-8", errors="replace")

            entries.append({"name": name, "inode": inode_no})
            offset += rec_len
            if offset >= max_size:
                break
        return entries

    def parse_gdts(self):
        stride = self._sb["gdt_size"]
        gdt_table_size = math.ceil((stride * self._block_group_count) / self._sb["block_size"])
        gdt_offset = 2 if self._sb["block_size"] == 1024 else 1

        gdts = self.read_blocks(gdt_offset, gdt_table_size)
        self._gdts = []

        for i in range(self._block_group_count):
            base = i * stride
            inode_table_lo = struct.unpack_from("<I", gdts, base + 0x08)[0]
            inode_table_hi = 0
            if stride >= 64:
                inode_table_hi = struct.unpack_from("<I", gdts, base + 0x28)[0] & 0xFFFF
            inode_table = (inode_table_hi << 32) | inode_table_lo
            self._gdts.append(inode_table)


def main(filename):
    with open(filename, "rb") as f:
        drive = Drive(f, bps=512)
        fs = EXT(drive)
        fs.parse_superblock()
        fs.parse_gdts()
        root_inode = fs.get_inode(2)
        entries = fs.parse_directory(root_inode)
        for e in entries:
            print(f"{e['name']} {e['inode']}")

if __name__ == "__main__":
    main(sys.argv[1])