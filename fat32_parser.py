import sys
import struct

def read_sector(f, sector, count=1):
    f.seek(sector*512)
    return f.read(count*512)

def read_fat_chain(start, fat):
    chain = []
    seen = set()
    eof = 0x0FFFFFF8
    cur = start

    while cur not in seen:
        seen.add(cur)
        chain.append(cur)
        entry = struct.unpack_from("<I", fat, cur*4)[0] & 0x0FFFFFFF
        if entry >= eof or entry == 0:
            break
        cur = entry

    return chain

def main(image_path, start_cluster):
    with open(image_path, "rb") as f:
        vbr = read_sector(f, 0)
        bps, spc, rsv_count, num_fats = struct.unpack_from("<HBHB", vbr, 11)
        fat_size = struct.unpack_from("<I", vbr, 36)[0]
        fat = read_sector(f, rsv_count, fat_size)
    chain = read_fat_chain(start_cluster, fat)
    print(",".join(map(str, chain)))

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2], 0))