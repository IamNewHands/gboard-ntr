#!/usr/bin/env python3
"""从 Mach-O 二进制里读 Objective-C 类表，按名字或 selector 检索。

用途：改 Gboard 的 dylib 之前，先确认「要反射调用的类/方法在这个二进制里真的存在、
方法名和类型编码是什么」。比在源码里猜、比真机崩溃后再回头查都快。

用法：
    python tools/objc_probe.py <macho> --class GKBLanguageID
    python tools/objc_probe.py <macho> --selector currentLanguage isChinese
    python tools/objc_probe.py <macho> --class-re 'Language' --limit 50
    python tools/objc_probe.py <macho> --classes        # 只数一下有多少类

多个二进制可以给多次 --bin 一并检索（比如 appex + gboard_framework）。

限制：只支持 64 位小端 Mach-O（MH_MAGIC_64，即 arm64 的 iOS 产物）；
不解符号表、不反汇编，只读 __objc_classlist / __objc_catlist。
"""
import argparse
import re
import struct
import sys


class MachO:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.d = f.read()
        self.path = path
        if self.d[:4] != b"\xcf\xfa\xed\xfe":
            raise SystemExit("%s: not a 64-bit little-endian Mach-O" % path)
        ncmds = struct.unpack_from("<I", self.d, 16)[0]
        off = 32
        self.segs = {}
        for _ in range(ncmds):
            cmd, size = struct.unpack_from("<II", self.d, off)
            if cmd == 0x19:  # LC_SEGMENT_64
                seg = self.d[off + 8:off + 24].split(b"\0")[0].decode()
                nsects = struct.unpack_from("<I", self.d, off + 64)[0]
                soff = off + 72
                for _ in range(nsects):
                    sname = self.d[soff:soff + 16].split(b"\0")[0].decode()
                    addr, sz, foff = struct.unpack_from("<QQI", self.d, soff + 32)
                    self.segs[seg + "," + sname] = (addr, sz, foff)
                    soff += 80
            off += size

    def vm2off(self, a):
        for (va, vs, fo) in self.segs.values():
            if va <= a < va + vs and vs:
                return fo + (a - va)
        return None

    def cstr(self, a):
        o = self.vm2off(a)
        if o is None:
            return None
        e = self.d.index(b"\0", o)
        return self.d[o:e].decode("utf-8", "replace")

    def u64(self, a):
        o = self.vm2off(a)
        return struct.unpack_from("<Q", self.d, o)[0] if o is not None else 0

    def u32(self, a):
        o = self.vm2off(a)
        return struct.unpack_from("<I", self.d, o)[0] if o is not None else 0

    def mlist(self, ml):
        res = []
        if not ml:
            return res
        fe = self.u32(ml)
        n = self.u32(ml + 4)
        rel = bool(fe & 0x80000000)
        ent = fe & 0xFFFF
        if ent < 8:
            ent = 12 if rel else 24
        for i in range(n):
            e = ml + 8 + i * ent
            if rel:
                o1 = struct.unpack_from("<i", self.d, self.vm2off(e))[0]
                o2 = struct.unpack_from("<i", self.d, self.vm2off(e + 4))[0]
                sel, typ = self.cstr(e + o1), self.cstr(e + 4 + o2)
            else:
                sel, typ = self.cstr(self.u64(e)), self.cstr(self.u64(e + 8))
            if sel:
                res.append((sel, typ))
        return res

    def classes(self):
        out = {}
        for key in ("__DATA_CONST,__objc_classlist", "__DATA,__objc_classlist"):
            if key not in self.segs:
                continue
            va, vs, fo = self.segs[key]
            for i in range(vs // 8):
                p = struct.unpack_from("<Q", self.d, fo + i * 8)[0]
                if not p:
                    continue
                data = self.u64(p + 32) & ~7
                name = self.cstr(self.u64(data + 24))
                if not name:
                    continue
                isa = self.u64(p)
                mdata = self.u64(isa + 32) & ~7
                out[name] = (self.mlist(self.u64(data + 32)), self.mlist(self.u64(mdata + 32)))
        return out

    def categories(self):
        res = []
        for key in ("__DATA_CONST,__objc_catlist", "__DATA,__objc_catlist"):
            if key not in self.segs:
                continue
            va, vs, fo = self.segs[key]
            for i in range(vs // 8):
                p = struct.unpack_from("<Q", self.d, fo + i * 8)[0]
                if not p:
                    continue
                cname = self.cstr(self.u64(p))
                clsname = self.cstr(self.u64(p + 8))
                im = self.u64(p + 16)
                cm = self.u64(p + 24)
                res.append((cname, clsname, self.mlist(im), self.mlist(cm)))
        return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("binary", nargs="+", help="Mach-O 文件（appex、framework 或 dylib）")
    ap.add_argument("--class", dest="klass", action="append", default=[], help="精确类名，可重复")
    ap.add_argument("--class-re", dest="klass_re", default=None, help="类名正则")
    ap.add_argument("--selector", action="extend", nargs="+", default=[],
                    help="精确 selector，一次可给多个，也可重复本参数")
    ap.add_argument("--classes", action="store_true", help="只输出类数量与类名列表")
    ap.add_argument("--limit", type=int, default=40, help="每个列表最多打印多少条（默认 40）")
    args = ap.parse_args(argv)

    for path in args.binary:
        m = MachO(path)
        classes = m.classes()
        print("== %s: %d classes, %d categories" % (path, len(classes), len(m.categories())))
        if args.classes:
            names = sorted(classes)
            print("\n".join(names[:args.limit]))
            if len(names) > args.limit:
                print("... (%d more)" % (len(names) - args.limit))
            continue

        targets = [n for n in sorted(classes)
                   if n in args.klass or (args.klass_re and re.search(args.klass_re, n))]
        if args.klass or args.klass_re:
            for name in targets[:args.limit]:
                im, cm = classes[name]
                print("  [%s]  +%d/-%d" % (name, len(cm), len(im)))
                for sel, typ in cm:
                    print("    +%-38s %s" % (sel, typ))
                for sel, typ in im:
                    print("    -%-38s %s" % (sel, typ))

        if args.selector:
            want = set(args.selector)
            print("-- selectors %s" % ", ".join(sorted(want)))
            for name in sorted(classes):
                im, cm = classes[name]
                for sel, typ in cm:
                    if sel in want:
                        print("  +[%s %s] %s" % (name, sel, typ))
                for sel, typ in im:
                    if sel in want:
                        print("  -[%s %s] %s" % (name, sel, typ))
            for cname, clsname, im, cm in m.categories():
                for sel, typ in im + cm:
                    if sel in want:
                        print("  cat(%s) [%s %s] %s" % (cname, clsname, sel, typ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
