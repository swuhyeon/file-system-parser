import sys
import struct

def main(filename):
    with open(filename, "rb") as f:
        f.seek(2*512)
        partitions = f.read(32*512)

        for i in range(128):
            partition = partitions[i*128:(i+1)*128]
            
            if partition[0] == 0:
                break

            type_guid = ''.join(f"{b:02X}" for b in partition[0:16])

            first_lba, last_lba = struct.unpack("<QQ", partition[32:48])
            sector_count = last_lba - first_lba + 1

            print(f"{type_guid} {first_lba} {sector_count}")

if __name__ == "__main__":
    main(sys.argv[1])