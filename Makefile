OZC := ozc
OZFLAGS := --nowarnunused --nowarnunusedformals

.PHONY: all run test clean

all: Repl.ozf

Repl.ozf: Repl.oz
	$(OZC) $(OZFLAGS) -c $< -o $@

run: Repl.ozf
	./ozrepl

test: Repl.ozf
	./tests/test.sh

clean:
	rm -f Repl.ozf tests/session.out
