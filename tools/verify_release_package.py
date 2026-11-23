#!/usr/bin/env python3
"""只读校验一个 Release IPA 是否是「仅换了 libgkx.dylib」的那一份。

用法:
    python tools/verify_release_package.py <旧 IPA> <新 IPA> <CI 编出的 libgkx.dylib>

断言四件事：
  1. 新包 ZIP CRC 正常，文件清单与旧包完全一致（没有多删/多加原生文件）；
  2. 相对旧包发生变化（字节不同）的文件只有 libgkx.dylib；
  3. 包里的 libgkx.dylib 与 CI 产物逐字节相同，且权限是 0o755；
  4. 两个主二进制各自只加载一次 @rpath/libgkx.dylib。

通过后打印一份 JSON（体积 / SHA-256 / 变更文件 / 架构）。真机渲染永远标
NOT VERIFIED —— 这个脚本只能证明「包换对了」，证明不了「装上去不闪」。
"""
import hashlib
import json
import stat
import struct
import sys
import zipfile
from pathlib import Path

def sha(data):
    return hashlib.sha256(data).hexdigest()

def dylibs(data):
    assert data[:4] == bytes.fromhex('cffaedfe'), 'expected little-endian Mach-O 64'
    assert struct.unpack_from('<I', data, 4)[0] == 0x100000c, 'expected arm64'
    p, libs = 32, []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, p)
        assert size >= 8 and p + size <= len(data), 'invalid load command'
        if cmd in (0xc, 0x18, 0x8000001f):
            off = struct.unpack_from('<I', data, p + 8)[0]
            libs.append(data[p + off:p + size].split(b'\0', 1)[0].decode())
        p += size
    return libs

old_path, new_path, ci_path = map(Path, sys.argv[1:4])
ci = ci_path.read_bytes()
with zipfile.ZipFile(old_path) as old, zipfile.ZipFile(new_path) as new:
    assert new.testzip() is None, 'ZIP CRC failure'
    old_files = {n for n in old.namelist() if not n.endswith('/')}
    new_files = {n for n in new.namelist() if not n.endswith('/')}
    assert old_files == new_files, 'unexpected added/removed native files'
    changed = sorted(n for n in old_files if old.read(n) != new.read(n))
    targets = sorted(n for n in new_files if n.endswith('/libgkx.dylib'))
    assert targets and changed and all(n in targets for n in changed), 'changes outside injected dylib'
    for target in targets:
        assert new.read(target) == ci, 'IPA/CI dylib mismatch: ' + target
        assert stat.S_IMODE(new.getinfo(target).external_attr >> 16) == 0o755, 'dylib not executable'
    for binary in ('Payload/Gboard.app/Gboard', 'Payload/Gboard.app/PlugIns/Gboard.appex/Gboard'):
        assert binary in new_files and dylibs(new.read(binary)).count('@rpath/libgkx.dylib') == 1, 'injection identity changed'
    print(json.dumps({'ipa': str(new_path), 'bytes': new_path.stat().st_size, 'sha256': sha(new_path.read_bytes()), 'ci_dylib_sha256': sha(ci), 'ci_dylib_bytes': len(ci), 'crc': 'OK', 'unchanged_files': len(new_files) - len(changed), 'changed_files': changed, 'dylibs': targets, 'architectures': 'arm64', 'device_rendering': 'NOT VERIFIED'}, ensure_ascii=False, indent=2))