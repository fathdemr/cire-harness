import argparse


def transform(text, upper=False):
    if upper:
        text = text.upper()
    return text


def main():
    parser = argparse.ArgumentParser(description="Transform text")
    parser.add_argument("text")
    parser.add_argument("--upper", action="store_true", help="uppercase the text")
    args = parser.parse_args()
    print(transform(args.text, upper=args.upper))


if __name__ == "__main__":
    main()
