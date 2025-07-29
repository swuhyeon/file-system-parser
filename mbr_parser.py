import sys
import struct

def main(filename):
    with open(filename, "rb") as f:
        mbr = f.read(512)
        partitions = mbr[446:446+64]

        for i in range(4):
            entry = partitions[i*16:(i+1)*16]
            ptype = entry[4]
            start_lba = struct.unpack("<I", entry[8:12])[0]
            size = struct.unpack("<I", entry[12:16])[0]

            if ptype == 0x05 and size > 0:
                extended_base = start_lba
                next_ebr = start_lba
                while True:
                    f.seek(next_ebr * 512)
                    ebr = f.read(512)
                    if len(ebr) < 512:
                        break

                    l_entry = ebr[446:462]
                    l_ptype = l_entry[4]
                    l_start = struct.unpack("<I", l_entry[8:12])[0]
                    l_size = struct.unpack("<I", l_entry[12:16])[0]

                    if l_ptype in (0x0B, 0x0C):
                        fs_type = "FAT32"
                    elif l_ptype == 0x07:
                        fs_type = "NTFS"
                    else:
                        fs_type = None

                    if fs_type and l_size > 0:
                        print(f"{fs_type} {next_ebr + l_start} {l_size}")

                    n_start = struct.unpack("<I", ebr[470:474])[0]
                    if n_start == 0:
                        break
                    next_ebr = extended_base + n_start

            else:
                if ptype in (0x0B, 0x0C):
                    fs_type = "FAT32"
                elif ptype == 0x07:
                    fs_type = "NTFS"
                else:
                    fs_type = None

                if fs_type and size > 0:
                    print(f"{fs_type} {start_lba} {size}")

if __name__ == "__main__":
    main(sys.argv[1])