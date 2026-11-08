======================================================================
  PS5 FFPFSC PRO — Tools Directory
======================================================================

This directory contains standalone extraction utilities for PlayStation packages.

Included out-of-the-box:
  • shadpkg.exe (v2.1.0, MIT License) - multi-threaded PS4 PKG extractor
    Source & Releases: https://github.com/seregonwar/ShadPKG

Other supported extraction utilities (optional alternatives):
  • orbis-pub-cmd.exe  (Official Publishing Tools PKG extractor)
  • ps4-pkg-tool.exe   (PS4 PKG Tool command-line utility)
  • pkg_pfs_tool.exe   (Flatz PKG / PFS unpacker)

When any of these tools is present here or on your system PATH,
PS5 FFPFSC PRO automatically unpacks PS4 Fake PKGs (.pkg),
generates ShadowMount-compatible metadata (sce_sys/param.json),
and converts them directly into .ffpfsc containers for PS5.

Note on PS5 PKGs:
PS5 retail PKGs are hardware-encrypted with Sony Prospero SAMU keys
and cannot be decrypted on PC. For PS5 titles, dump them directly on
your jailbroken console with Itemzflow or Game Dumper (as a decrypted
folder, .exfat, or .ffpkg), which are fully supported natively.
======================================================================
