#!/usr/bin/env python3
"""把九键左列第 3 键与第 4 键的语义对调（符号 <-> 中英），可重复执行。

用法:
    python tools/nib_left_column.py --ipa <原始或已对调的.ipa> --out <输出.ipa>
    python tools/nib_left_column.py --ipa <ipa> --check      # 只报告状态

为什么要改 restorationIdentifier:
    left_column 里没有映射表，四个键的语义由 restorationIdentifier（left_1..left_4）
    决定，appex 里的 protobuf 布局表再把 ID 映射到 softkey。约束链
    left_2.top = left_1.bottom、left_3.top = left_2.bottom、left_4.top = left_3.bottom
    让位置完全由编号决定，所以交换 left_3 与 left_4 这两个字符串，等价于交换两个键的位置。
    两个字符串都是 20 字节，等长替换不改变 NIBArchive 的任何偏移或表长度。

幂等性:
    对调是自反的（连做两次等于没做），所以不能靠「再换一次」判断方向。
    这里用每个 nib 的固定 SHA-256 认状态：原包哈希 -> 对调；对调后哈希 -> 原样跳过；
    其他哈希 -> 直接报错，绝不猜测。CI 的 publish job 依赖这条保证。

实现要点:
    不重新序列化 nib，只在解包后的字节上做等长替换，其余字节逐字保留；
    回写时沿用原 zip 条目的权限与时间戳，口径与 tools/inject.py 一致。
"""

import argparse
import hashlib
import os
import shutil
import sys
import zipfile

LEFT_3 = b"key_pos_9keys_left_3"
LEFT_4 = b"key_pos_9keys_left_4"
PLACEHOLDER = b"key_pos_9keys_left_X"

# 三个 nib 的原包哈希与对调后的哈希。原包值同时钉在 tests/test_native_resources.py。
NIB_HASHES = {
    "keyboard_pinyin_ninekeys.nib": (
        "52df512c47ff33d683a4a8950bbb01182a4de08a9872a6676981362e8ba6995b",
        "862fc0042d8d480966b6b3a0dad2eef4db5c7dbadf8848d110324415d0ebf901",
    ),
    "keyboard_body_pinyin_9key_digit.nib": (
        "69e7c387ab0f7c38910ff8026c1637fa76354073f0549dc5589f033fa8428d69",
        "8dd679478772ca6d01017365aa09e8ab7385d7559144743bfbecff65fbdf75fe",
    ),
    "keyboard_body_pinyin_9key_symbol.nib": (
        "d62b38a9e43d8878dcb2305b48e4370cdc71e7abb357dd269bd8aefdeaa377ec",
        "a6071fd2d3761750db04a36b0baf787e11545c8d716a69c7a3ee667a49bd1933",
    ),
}

TARGET_NIBS = tuple(NIB_HASHES)


def swap_ids(raw):
    """等长交换 left_3 与 left_4，返回新字节。计数不是 1 就拒绝，避免误伤别的资源。"""
    for ident in (LEFT_3, LEFT_4):
        count = raw.count(ident)
        if count != 1:
            raise ValueError("%s 出现 %d 次，预期恰好 1 次" % (ident.decode(), count))
    return raw.replace(LEFT_3, PLACEHOLDER).replace(LEFT_4, LEFT_3).replace(PLACEHOLDER, LEFT_4)


def nib_state(name, raw):
    """返回 "original" / "swapped"；哈希对不上就报错，不做猜测。"""
    digest = hashlib.sha256(raw).hexdigest()
    original, swapped = NIB_HASHES[name]
    if digest == original:
        return "original"
    if digest == swapped:
        return "swapped"
    raise ValueError("%s 哈希不在预期内: %s" % (name, digest))


def ensure_swapped(archive):
    """返回 ({成员名: 新字节}, 状态计数)。已对调的 nib 不出现在返回值里。"""
    patched, counts = {}, {"original": 0, "swapped": 0}
    for name in archive.namelist():
        base = os.path.basename(name)
        if base not in NIB_HASHES:
            continue
        raw = archive.read(name)
        state = nib_state(base, raw)
        counts[state] += 1
        if state == "original":
            patched[name] = swap_ids(raw)
    return patched, counts


def main():
    parser = argparse.ArgumentParser(description="对调九键左列第 3、4 键的语义（幂等）")
    parser.add_argument("--ipa", required=True, help="输入 IPA")
    parser.add_argument("--out", help="输出 IPA；--check 时不需要")
    parser.add_argument("--check", action="store_true", help="只报告状态，不写文件")
    args = parser.parse_args()

    if not args.check and not args.out:
        parser.error("没有 --check 时必须给 --out")
    if args.check and args.out:
        parser.error("--check 与 --out 不能同时使用")

    with zipfile.ZipFile(args.ipa, "r") as src:
        infos = src.infolist()
        patched, counts = ensure_swapped(src)
        total = counts["original"] + counts["swapped"]
        if total != len(TARGET_NIBS):
            raise SystemExit("命中 %d 个 nib，预期 %d 个" % (total, len(TARGET_NIBS)))

        for name in patched:
            print("  对调 %s (%d B)" % (os.path.basename(name), len(patched[name])))
        for name in TARGET_NIBS:
            if name not in {os.path.basename(p) for p in patched}:
                print("  已是目标状态 %s" % name)

        if args.check:
            print("[check] 原包 %d / 已对调 %d，%s"
                  % (counts["original"], counts["swapped"],
                     "需要改写" if patched else "无需改动"))
            return 0

        if not patched:
            # 仍然产出 --out：CI 把它当中间产物直接喂给下一步，缺文件会断链。
            # 用 copy 而不是重打包，字节与输入完全一致。
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            shutil.copy2(args.ipa, args.out)
            print("输入已是目标状态，原样复制到 %s" % args.out)
            return 0

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        tmp = args.out + ".tmp"
        with zipfile.ZipFile(tmp, "w") as dst:
            for info in infos:
                data = patched.get(info.filename)
                if data is None:
                    data = src.read(info.filename)
                # 沿用原条目的时间戳与外部属性，权限位不变。
                dst.writestr(info, data)
        os.replace(tmp, args.out)

    print("输出 %s (%.2f MB)" % (args.out, os.path.getsize(args.out) / 1048576))
    with open(args.out, "rb") as handle:
        print("sha256 = %s" % hashlib.sha256(handle.read()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
