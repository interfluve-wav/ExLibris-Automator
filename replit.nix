{pkgs}: {
  deps = [
    pkgs.lsof
    pkgs.tigervnc
    pkgs.x11vnc
    pkgs.xorg.xorgserver
    pkgs.libgbm
    pkgs.udev
    pkgs.libxkbcommon
    pkgs.expat
    pkgs.alsa-lib
    pkgs.pango
    pkgs.cairo
    pkgs.mesa
    pkgs.xorg.libXfixes
    pkgs.xorg.libXdamage
    pkgs.xorg.libXcomposite
    pkgs.at-spi2-core
    pkgs.xorg.libxcb
    pkgs.cups
    pkgs.at-spi2-atk
    pkgs.atk
    pkgs.dbus
    pkgs.nss
    pkgs.nspr
  ];
}
