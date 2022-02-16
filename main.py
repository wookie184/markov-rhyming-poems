import random
import string
import requests
from typing import Optional, NamedTuple, Union

CORPUS_PATHS = {
    "SHAKESPEARE": "corpuses/shakespeare_corpus.txt",
    "KEATS": "corpuses/john_keats_corpus.txt",
    "BLAKE": "corpuses/william_blake_corpus.txt",
    "WORDSWORD": "corpuses/william_wordsworth_corpus.txt",
}

class PoemSettings(NamedTuple):
    # length of this is number of lines in poem
    line_lengths: list[int]

    break_lines: list[int]
    rhyme_map: dict[int, int]

    @classmethod
    def from_rhyme_scheme(cls, rhyme_scheme: str, line_lengths: Union[int, list[int]]=7):
        poem_length, rhyme_map, break_lines = parse_rhyme_scheme(rhyme_scheme)

        if isinstance(line_lengths, int):
            line_lengths = [line_lengths for _ in range(poem_length)]

        return cls(line_lengths, break_lines, rhyme_map)


def parse_rhyme_scheme(scheme):
    line_num = 0
    rhyme_scheme = {}
    break_lines = set()
    for char in scheme:
        if char == '/':
            break_lines.add(line_num)
            continue
        rhyme_scheme.setdefault(char, []).append(line_num)
        line_num += 1
    
    rhyme_map = {}
    for rhyme_group in rhyme_scheme.values():
        for line, nxt in zip(rhyme_group, rhyme_group[1:]):
            rhyme_map[line] = nxt
    return line_num, rhyme_map, break_lines


class ReverseMarkovChain:
    """
    A reversed markov chain implementation.

    With a normal markov chain you would start by picking a random word that could begin a sentence
    and use the chain to continue from there. However, after that point it is very difficult to control
    what results you get, and as for the poem we want to ensure we can end lines with rhyming words, this
    can be hard to do.

    To tackle this we instead start with the rhyming words, and work backwards from there.
    """
    def __init__(self, texts: list):
        self.chaindict = self.generate_chain(texts)
        self.endings = self.collect_endings(texts)

    @classmethod
    def from_corpuses(cls, *corpuses):
        poems = []
        for path in corpuses:
            with open(path, "r", encoding="utf8") as f:
                corpus = f.read()
            poems.extend(corpus.split('\n\n'))

        return cls(poems)

    def generate_chain(self, texts: list[str]) -> dict[str, dict[str, int]]:
        """
        Generates a markov chain based of the list of texts given.
        
        The format is dict with keys as words, and values as dicts mapping each word that
        preceeds it to the number of times it does. Newlines are considered the same as spaces
        in terms of words following eachother, and punctutation is considered part of a word.

        All text is converted to lowercase.

        For example, "How are you are you good?" becomes:
        {'are': {'how': 1, 'you': 1}, 'you': {'are': 2}, 'good?': {'you': 1}}
        """
        chain = {}
        for text in texts:
            # Split full text into list of words
            words = [word.lower() for word in text.split()]

            # Sliding window over pairs of words
            for prev_word, word in zip(words, words[1:]):
                # Note this is where they are added in reverse
                chain.setdefault(word, {}).setdefault(prev_word, 0)
                chain[word][prev_word] += 1
        
        return chain

    def collect_endings(self, texts: list) -> list:
        """Return a list of all words that end lines in the texts given."""
        endings = []
        for text in texts:
            for line in text.split("\n"):
                if line:
                    endings.append(line.rsplit(maxsplit=1)[-1].lower())
        return endings

    def generate_sentence(self, end: str, length: int=3):
        """
        Takes the word to end the sentence, and an optional length, and
        generates a sentence using a markov chain.
        """
        sentence = []
        curr_word = end
        for _ in range(length):  # length of sentence
            sentence.append(curr_word)
            try:
                possible_words = self.chaindict[curr_word]
            except KeyError:
                # Word does not have any words before it anywhere in corpus
                # this happens quite rarely, so just choose a random word
                curr_word = random.choice(list(self.chaindict.keys()))
            else:
                curr_word = self.choose_value(possible_words)
        # Reverse the result so it is back in the right direction
        return sentence[::-1]

    def choose_value(self, possible: dict[str, int]) -> str:
        """Chooses a random key from the dictionary using the values as weights."""
        return random.choices(list(possible.keys()), possible.values())[0]


class MarkovPoem:
    def __init__(self, markov_chain: ReverseMarkovChain, settings: PoemSettings):
        self.chain = markov_chain
        self.settings = settings
        self.used_rhymes = []

    def generate_poem(self):
        rhymes = {}
        for line_num, line_length in enumerate(self.settings.line_lengths):
            if line_num in self.settings.break_lines:
                yield ""

            # If it's a rhyming line it will start with the rhyme word already in rhymes
            # otherwise it will use a random ending
            end = rhymes.get(line_num) or random.choice(self.chain.endings)
            self.used_rhymes.append(self.clean_for_rhyme(end))

            line = self.chain.generate_sentence(end, length=line_length)

            if line_num in self.settings.rhyme_map:
                rhymes[self.settings.rhyme_map[line_num]] = self.get_rhyme(line[-1])

            yield line

    def get_rhyme(self, word: str) -> Optional[str]:
        word = self.clean_for_rhyme(word)
        urls = [
            f"https://api.datamuse.com/words?rel_rhy={word}",
            f"https://api.datamuse.com/words?rel_nry={word}"
        ]
        for url in urls:
            res = requests.get(url)
            for rhyme_info in res.json():
                rhyme = rhyme_info["word"]
                if rhyme in self.chain.chaindict and rhyme not in self.used_rhymes:
                    return rhyme
        return None

    @staticmethod
    def clean_for_rhyme(word: str):
        """
        Converts the word given into a form more recogniseable by the rhyme api
        
        For example, "warm'd" becomes "warmed"
        """
        # Remove any surrounding punctuation
        word = word.strip(string.punctuation)

        # For things like know'st
        # Results in non-perfect rhymes but better than nothing
        word = word.removesuffix("'st")

        # Check for endings like 'n or 'd which should become en or ed
        if word.endswith("'d") or word.endswith("'n"):
            word = word[:-2] + "e" + word[-1]

        # o'er and e'er become over and ever
        word = word.replace("o'e", "ove").replace("e'e", "eve")

        # Finally, remove any non ascii characters
        word = ''.join(char for char in word if char in string.ascii_letters)
        return word


def main():
    print("Shakespeare poem with aaaa/bbbb/cccc rhyme scheme:")
    chain = ReverseMarkovChain.from_corpuses(CORPUS_PATHS["SHAKESPEARE"])
    settings = PoemSettings.from_rhyme_scheme("aaaa/bbbb/cccc")
    poem = MarkovPoem(chain, settings)
    for line in poem.generate_poem():
        print(' '.join(line).capitalize())

    print("\n")

    print("John Keats poem with aa/bb/cc/dd rhyme scheme and varying line lengths:")
    chain = ReverseMarkovChain.from_corpuses(CORPUS_PATHS["KEATS"])
    settings = PoemSettings.from_rhyme_scheme("aa/bb/cc/dd", range(2, 10))
    poem = MarkovPoem(chain, settings)
    for line in poem.generate_poem():
        print(' '.join(line).capitalize())
        

if __name__ == "__main__":
    main()