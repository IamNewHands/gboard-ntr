# Gboard-NTR (iOS Gboard enhancement patch)

[中文](README.md) | **English**

A no-source reverse-engineering patch for the official **iOS Gboard 2.3.19**: an Objective-C dylib (`libgkx.dylib`) is injected into the stock app, combined with lossless binary rewriting.

> **Design philosophy: stay native.** The stock Google Mozc Pinyin engine, the original key layouts and Glide Typing are kept intact. No added keyboard height, no view occlusion, no touch interception.

---

## What it does

**1. Bundled Rime "Wanxiang" dictionary**
60,000 curated entries, slimmed down to a 1.61 MB file. Copied into the App Group container on first launch, so it works out of the box without inflating the install size.

**2. Nine-key action key: retype / dismiss / newline**
Only the native emoji key on the nine-key layout and its symbol pages is replaced; the 26-key layout and the return key stay untouched. It shows **重输 (retype)** while composing, **收起 (dismiss)** when there are suggestions but no composition, and **换行 (newline)** when idle. Native background and colours are preserved, with no added height or occlusion, and switching pages no longer flashes the native emoji.

**3. G-logo page trimming**
The YouTube, Contacts, GIF and Sticker pages are removed, leaving emoji, kaomoji and the built-in pages. Any class missing from a future Gboard build is skipped.

**4. Phrases**
A "常用语" page is added to the G-logo picker and follows the keyboard skin. With pinning off, tapping a phrase inserts it and closes the panel; with pinning on, the panel stays open. It can be edited inside the keyboard, and Settings → Gboard → Phrases in the main app is a second entry point.

**5. Punctuation long-press popup**
Holding the nine-key "，。？！" key for 0.32 s shows a row of symbols; slide to one and release to insert it. The symbol list and the count (1–10) are editable in the main app, and the colours follow the keyboard skin.

**6. Diagnostic log (off by default)**
Nothing is recorded by default. The switch lives in Settings → Gboard → Diagnostic log and takes effect across processes within half a second.

**7. "中/英" label on the language key**
The language key (3rd key of the nine-key left column and the top-right key of the 26-key layout) ships with a globe icon only; it now shows 中 and 英, the current language fully opaque and the other dimmed. The overlay is purely visual — touches and language switching stay on the native path — and switching language or pages no longer flashes the globe.

**8. Nine-key left column order**
Top to bottom: 123 / pinyin / language / symbols. The original build has the language key fourth and symbols third, so the injection swaps the two restoration identifiers; the Auto Layout chain is untouched, which means no extra constraints and no flicker when switching pages.

---

## Development red lines

1. **Never touch the keyboard root constraints or height** — candidates get pushed off-screen or gaps appear.
2. **Never intercept key touch events** — Glide Typing is sensitive to touch continuity; only an independent subview on the target key is allowed.
3. **Dictionary limits are hard** — at most 70,000 entries and 2.5 MB, with redundant fields omitted, or Jetsam kills the extension.
4. **Windows packaging must preserve Unix modes** — 0o755 for executables, 0o644 for data files, or signing fails or the extension is killed.
5. **Lossless injection** — write `LC_LOAD_DYLIB` only into the zero padding after the load commands; rewrite App Groups at equal length.

---

## Repository layout

```
gboard-ntr/
├── dylib/                     # injected source (gkx.m and headers)
├── tools/
│   ├── inject.py              # Mach-O injection + App Group rewrite + Unix modes
│   ├── dict_converter.py      # Wanxiang dictionary → compact Protobuf
│   ├── inspect_signed.py      # read-only Mach-O / permission self-check
│   ├── swap_dylib.py          # replace libgkx.dylib inside a packed IPA (CI)
│   ├── verify_release_package.py # read-only: only the dylib changed, and it matches CI
│   └── publish_release.py     # publish to GitHub Release
├── tests/                     # source-level contract tests
├── .github/workflows/         # CI: build dylib → swap → publish
├── dist/                      # build output
├── README.md / README.en.md
└── agent.md                   # reverse-engineering notes and pitfalls
```

---

## Build and publish

**CI does everything (normal path)**: push a change under `dylib/`. CI compiles the new `libgkx.dylib`, downloads the released IPA, swaps the dylib inside it, then re-uploads and refreshes the release body.

**Local packaging** (when the dictionary or injection logic changed):

```powershell
# 1. Convert the dictionary (optional)
python tools/dict_converter.py --dir "%APPDATA%\Rime\dicts" -o "dist/user_dictionary.db" --max 60000

# 2. Inject and repack
python tools/inject.py --ipa "../ipa/Gboard_2.3.19.ipa" --dylib "dist/libgkx.dylib" `
  --dict "dist/user_dictionary.db" --app-group "group.zunbengege.top" `
  --out "dist/gboard-ntr-1.0-unsigned.ipa"

# 3. Publish
python tools/publish_release.py --asset dist/gboard-ntr-1.0-unsigned.ipa --refresh-sha
```

`--app-group` is mandatory; without it the app crashes on launch and the keyboard stays on 26 keys. When using your own provisioning profile, `GXKGroup` in `dylib/gkx.m`, the default in `inject.py` and this flag must all match.

Fixed download URL:
```
https://github.com/IamNewHands/gboard-ntr/releases/latest/download/gboard-ntr-1.0-unsigned.ipa
```

---

## Install

1. Self-sign with **LCSign**, SideStore, TrollStore or similar and install.
2. Enable **Allow Full Access** in Settings → General → Keyboard → Keyboards → Gboard (the dictionary and configuration depend on the App Group).
3. If nothing changed after an overwrite install, remove the keyboard and add it again, or restart the host app.

---

## ⚠️ Disclaimer and license

* This repository contains **no** Google binary and no IPA — only injection source, dictionary tooling and documentation. You must obtain a genuine **Gboard 2.3.19** IPA yourself.
* Patched builds are for **personal, self-signed testing only**. Do not redistribute or use commercially. Gboard and Mozc remain the property of Google.
* Provisioning profiles, certificates and App Groups are your responsibility; `group.zunbengege.top` is a placeholder.
* The patch performs unsigned binary injection; behaviour may change after a system or signing-tool update. Use at your own risk.
