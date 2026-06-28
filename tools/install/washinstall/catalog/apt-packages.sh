#!/usr/bin/env bash
# apt install script — generated from tools.toml.
# Usage: bash apt-packages.sh   (review before running)
set -euo pipefail

sudo apt-get update

# === Baseline (install once) ===
sudo apt-get install -y \
  grep \
  ripgrep \
  sed \
  perl \
  gawk \
  coreutils \
  bsdmainutils \
  datamash \
  moreutils \
  parallel \
  findutils \
  fd-find \
  diffutils \
  patch \
  jq \
  xmlstarlet \
  miller \
  sqlite3 \
  pandoc \
  poppler-utils \
  graphviz \
  libc-bin \
  dos2unix \
  xxd \
  gettext-base \
  python3

# === Full set (uncomment the block to add) ===
# sudo apt-get install -y \
#   silversearcher-ag \
#   ack \
#   pcre2-utils \
#   ed \
#   util-linux \
#   coreutils \
#   pv \
#   git-delta \
#   wdiff \
#   jo \
#   crudini \
#   libxml2-utils \
#   html-xml-utils \
#   html2text \
#   lynx \
#   tesseract-ocr \
#   ocrmypdf \
#   pdfgrep \
#   mupdf-tools \
#   catdoc \
#   libreoffice \
#   plantuml \
#   libgraph-easy-perl \
#   gnuplot \
#   chafa \
#   figlet \
#   qrencode \
#   espeak-ng \
#   recode \
#   binutils \
#   m4 \
#   ruby \
#   nodejs \
#   php-cli \
#   r-base \
#   bc \
#   aspell \
#   codespell

# === Not in apt — install another way ===
# sd: cargo install sd (not in apt)
# frawk: cargo install frawk
# goawk: release binary
# choose: cargo install choose
# hck: cargo install hck
# teip: cargo install teip
# gron: go install / release
# fx: npm i -g fx / release
# jc: pipx install jc
# yq (mikefarah): snap/go (Go version); apt 'yq' may be the python one
# dasel: release binary
# taplo: cargo install taplo-cli
# pup: go install / release
# htmlq: cargo install htmlq
# xidel: release binary
# qsv: cargo install qsv
# xsv: cargo install xsv
# csvkit: pipx install csvkit
# csvq: go install / release
# dsq: release binary
# q: pipx install q-text-as-data
# duckdb: release binary / pipx install duckdb
# octosql: release binary
# ast-grep (sg): cargo install ast-grep
# comby: release binary
# srgn: cargo install srgn
# tree-sitter (+ tsq): cargo install / npm
# mq: cargo install mq-cli
# glow: release binary
# mermaid-cli (mmdc): npm i -g @mermaid-js/mermaid-cli
# termgraph: pipx install termgraph
# whisper.cpp: build from source
# hexyl: cargo install hexyl
# jinja2 (j2cli / jinja2-cli): pipx install jinja2-cli
# pyp: pipx install pyp
# nushell (nu): release / cargo install nu
# llm: pipx install llm
# ttok: pipx install ttok
# strip-tags: pipx install strip-tags
# files-to-prompt: pipx install files-to-prompt
# ollama: install script / release
# mods: release binary
# aichat: cargo install aichat
# fabric: go install / release
