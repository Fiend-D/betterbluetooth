# Build image for the Linux release: Debian 11 (glibc 2.31) so binaries run on Ubuntu 20.04+ / Debian 11+.
FROM python:3.12-bullseye

RUN rm -f /etc/apt/sources.list.d/* \
    && printf 'deb http://archive.debian.org/debian bullseye main\ndeb http://archive.debian.org/debian-security bullseye-security main\n' \
        > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update && apt-get install -y --no-install-recommends \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
        libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 libxkbcommon0 libxkbcommon-x11-0 \
        libegl1 libgl1 libfontconfig1 libfreetype6 libdbus-1-3 libglib2.0-0 libwayland-client0 \
        libwayland-cursor0 libwayland-egl1 file wget ca-certificates desktop-file-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "PySide6-Essentials==6.9.3" "dbus-fast>=2.0" "pyinstaller>=6.10" \
    && wget -q -O /usr/local/bin/appimagetool \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
    && chmod +x /usr/local/bin/appimagetool

ENV APPIMAGE_EXTRACT_AND_RUN=1
WORKDIR /src
