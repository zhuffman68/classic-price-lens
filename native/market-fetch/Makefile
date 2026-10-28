CC ?= cc
OUT ?= lupin-market-fetch
CFLAGS += -std=c11 -Os -Wall -Wextra -Werror
WEBKIT_FLAGS := $(shell pkg-config --cflags --libs webkit2gtk-4.1)

$(OUT): market_fetch_linux.c
	$(CC) $(CFLAGS) $< -o $@ $(WEBKIT_FLAGS)
