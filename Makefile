OZC := ozc
OZFLAGS := --nowarnunused --nowarnunusedformals

.PHONY: all run test clean

all: Repl.ozf

Repl.ozf: ozrepl/Repl.oz
	$(OZC) $(OZFLAGS) -c $< -o $@

run: Repl.ozf
	python3 -m ozrepl

test: Repl.ozf
	./tests/test.sh

clean:
	rm -f Repl.ozf tests/session.out
