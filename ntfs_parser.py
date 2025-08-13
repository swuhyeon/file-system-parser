import sys
import struct

def read_vbr(f):
    f.seek(0)
    vbr = f.read(512)
    if len(vbr) != 512:
        raise ValueError("Invalid VBR")
    bps, spc = struct.unpack_from("<HB", vbr, 11)
    mft_lcn   = struct.unpack_from("<Q", vbr, 48)[0]
    cpr       = struct.unpack_from("<b", vbr, 64)[0]
    cluster_size = bps * spc
    mft_record_size = (1 << (-cpr)) if cpr < 0 else cpr * cluster_size
    return bps, spc, mft_lcn, cluster_size, mft_record_size

def get_runlist(record):
    first_attr_off = struct.unpack_from("<H", record, 20)[0]
    off = first_attr_off
    while off + 4 <= len(record):
        attr_type = struct.unpack_from("<I", record, off)[0]
        if attr_type == 0xFFFFFFFF:
            break
        attr_len = struct.unpack_from("<I", record, off + 4)[0]
        if attr_len == 0:
            break
        non_res = record[off + 8]
        if attr_type == 0x80 and non_res != 0:
            run_off = struct.unpack_from("<H", record, off + 32)[0]
            return bytes(record[off + run_off: off + attr_len])
        off += attr_len
    return None

def parse_runlist(run_bytes):
    runs, i, prev_lcn = [], 0, 0
    while i < len(run_bytes):
        header = run_bytes[i]
        i += 1
        if header == 0:
            break
        len_len = header & 0x0F
        off_len = header >> 4
        run_len = int.from_bytes(run_bytes[i:i+len_len], "little", signed=False)
        i += len_len
        run_off = int.from_bytes(run_bytes[i:i+off_len], "little", signed=True)
        i += off_len
        lcn = prev_lcn + run_off
        runs.append((lcn, run_len))
        prev_lcn = lcn
    return runs

def main(filename):
    with open(filename, "rb") as f:
        bps, spc, mft_lcn, cluster_size, mft_record_size = read_vbr(f)
        f.seek(mft_lcn * cluster_size)
        record = f.read(mft_record_size)
        run_bytes = get_runlist(record)

    runs = parse_runlist(run_bytes)

    print(sum(length for _, length in runs))
    for lcn, length in runs:
        print(f"{lcn} {length}")

if __name__ == "__main__":
    main(sys.argv[1])