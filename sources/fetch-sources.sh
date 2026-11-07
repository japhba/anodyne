#!/bin/sh
# The fonts Anodyne is built from, into ./src: Lisnoti (the commit Anodyne's files were built from)
# and Google's variable Noto Sans and Noto Sans Math.
set -e
mkdir -p src/noto
if [ ! -d src/lisnoti ]; then
  git clone https://github.com/Lisnoti/Lisnoti src/lisnoti
  git -C src/lisnoti checkout -q 6642e5b5783d4e42eb6f447e6215138662b8e53d
fi
for f in 'NotoSans[wdth,wght].ttf' 'NotoSans-Italic[wdth,wght].ttf'; do
  url=$(printf '%s' "$f" | sed 's/\[/%5B/; s/\]/%5D/')
  curl -fsSL -o "src/noto/$f" "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/$url"
done
# (its dotless i and j for accents, dtls)
curl -fsSL -o src/noto/NotoSansMath-Regular.ttf https://raw.githubusercontent.com/google/fonts/main/ofl/notosansmath/NotoSansMath-Regular.ttf
echo "sources in ./src"
