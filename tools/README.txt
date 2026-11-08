======================================================================
  PS5 FFPFSC PRO — Tools Directory
======================================================================

This directory contains standalone extraction utilities for PlayStation packages.

Included out-of-the-box:
  • ProsperoPkgTool.exe / ProsperoPkgTool (v0.3, MIT License)
    Clean-room multiplatform PS5 package toolkit (no Sony tools or hardware keys needed).
    Extracts PS5 Fake PKGs (FPKGs) on PC with the standard 0x00 zero passcode.
    Source: https://github.com/pearlxcore/ProsperoPkgTool

  • shadpkg.exe / shadpkg-debian (v2.1.0, MIT License)
    High-performance multi-threaded PS4 PKG extractor.
    Source: https://github.com/seregonwar/ShadPKG

Other supported extraction utilities (optional alternatives):
  • prospero-pub-cmd.exe (Official Prospero PS5 Publishing Tools extractor)
  • orbis-pub-cmd.exe    (Official Orbis PS4 Publishing Tools extractor)
  • ps4-pkg-tool.exe     (PS4 PKG Tool command-line utility)
  • pkg_pfs_tool.exe     (Flatz PKG / PFS unpacker)

When these tools are present, PS5 FFPFSC PRO automatically unpacks both
PS4 PKGs and PS5 Fake PKGs (.pkg), extracts outer CNT metadata
(sce_sys/param.json, icon0.png, pics), and converts them directly into
ShadowMount-compatible .ffpfsc containers for PS5.

Note on PS5 Retail PKGs:
PS5 retail (non-fake) PKGs are hardware-encrypted with Sony Prospero SAMU
keys and cannot be decrypted on PC without console hardware.
For retail PS5 titles, dump them directly on your jailbroken console with
Itemzflow or Game Dumper as a decrypted folder (/app0/), .exfat, or .ffpkg.
======================================================================
