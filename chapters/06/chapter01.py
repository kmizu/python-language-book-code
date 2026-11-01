class Token:
    def __init__(self, kind, text, pos):
        self.kind = kind
        self.text = text
        self.pos = pos


SYMBOLS = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "(": "LPAREN",
    ")": "RPAREN",
}


def lex(source):
    tokens = []
    i = 0

    while i < len(source):
        ch = source[i]

        if ch.isspace():
            i += 1
            continue

        if "0" <= ch <= "9":
            start = i
            while i < len(source) and "0" <= source[i] <= "9":
                i += 1
            tokens.append(Token("INT", source[start:i], start))
            continue

        if ch in SYMBOLS:
            tokens.append(Token(SYMBOLS[ch], ch, i))
            i += 1
            continue

        raise ValueError(f"{i + 1}文字目の{ch!r}は読めません")

    tokens.append(Token("EOF", "", len(source)))
    return tokens


if __name__ == "__main__":
    for token in lex("100 + 80 * 3"):
        print(token.kind, repr(token.text), token.pos)
