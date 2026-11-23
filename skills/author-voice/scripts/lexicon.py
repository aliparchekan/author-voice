"""Word lists used by fingerprint.py and check.py.

Filler markers are words and phrases that language models overuse in
academic prose. They are not banned: some authors use a few of them. check.py
flags a marker only when a draft uses it more often than the author did.
"""

FUNCTION_WORDS = """
a about above after again against all also although among an and any are as at
be because been before being below between both but by can could did do does
doing down during each either even ever every few for from further had has have
having here how however i if in into is it its itself just less many may might
more most much must neither no nor not now of off on once one only or other our
out over own same several shall should since so some such than that the their
them then there these they this those though through thus to too under until up
upon very via was we were what when where whereas whether which while who whom
whose why will with within without would yet
""".split()

TRANSITIONS = [
    "however", "in contrast", "as a result", "thus", "hence", "therefore",
    "moreover", "furthermore", "in addition", "additionally", "consequently",
    "note that", "on the other hand", "first", "second", "finally", "next",
    "then", "similarly", "nevertheless", "in particular", "for instance",
    "for example", "indeed", "to this end", "specifically", "in this case",
    "as expected", "interestingly", "on the contrary", "instead", "otherwise",
]

HEDGES = [
    "may", "might", "could", "possibly", "likely", "approximately", "about",
    "around", "roughly", "suggests", "suggest", "appears", "appear", "seems",
    "seem", "rather", "somewhat", "generally", "typically", "essentially",
    "slightly", "mainly", "mostly", "fairly",
]

FILLER = [
    "delve", "delves", "crucial", "crucially", "pivotal", "notably",
    "furthermore", "moreover", "additionally", "comprehensive", "robust",
    "robustness", "leverage", "leverages", "leveraging", "seamless",
    "seamlessly", "underscore", "underscores", "underscoring", "showcase",
    "showcases", "showcasing", "highlight", "highlights", "highlighting",
    "valuable insights", "insights", "landscape", "realm", "intricate",
    "multifaceted", "paving the way", "paves the way", "sheds light",
    "shed light", "a testament to", "holistic", "nuanced", "meticulous",
    "meticulously", "fostering", "foster", "harness", "harnessing", "unlock",
    "unlocking", "navigate", "navigating", "elevate", "streamline",
    "cutting-edge", "groundbreaking", "remarkable", "remarkably",
    "it is worth noting", "it is important to note", "it should be noted",
    "plays a crucial role", "plays a key role", "plays a pivotal role",
    "plays a vital role", "a myriad of", "myriad", "vital", "essential",
    "enhance", "enhances", "enhanced", "enhancing", "facilitate",
    "facilitates", "ensure", "ensures", "ensuring", "key insight",
    "noteworthy", "intriguing", "compelling", "superior performance",
    "significantly outperforms", "in summary", "overall", "in conclusion",
    "these results demonstrate", "this demonstrates", "this highlights",
    "these findings", "in essence", "ultimately", "effectively", "notable",
    "substantial", "substantially", "significant", "significantly",
]

# Last sentences of a paragraph that start like this usually restate it.
FORMULAIC_CLOSER_OPENERS = [
    "these results", "this result", "these findings", "this demonstrates",
    "this shows", "this highlights", "this confirms", "this underscores",
    "overall", "in summary", "in conclusion", "taken together",
    "collectively", "together, these", "thus, the proposed",
    "therefore, the proposed", "this further", "these observations",
]

ABBREVIATIONS = [
    "e.g.", "i.e.", "et al.", "Fig.", "Figs.", "Eq.", "Eqs.", "Sec.", "Secs.",
    "Ref.", "Refs.", "vs.", "cf.", "resp.", "approx.", "No.", "Tab.", "Thm.",
    "Prop.", "Lem.", "Def.", "Ch.", "pp.", "Dr.", "Prof.", "St.", "a.k.a.",
    "w.r.t.", "etc.",
]

# Acronyms a reader in signal processing/communications needs no definition for.
COMMON_ACRONYMS = {
    "5G", "6G", "4G", "3G", "LTE", "GPS", "GNSS", "IEEE", "MATLAB", "USA",
    "EU", "PDF", "CDF", "RMSE", "MSE", "SNR", "dB", "dBm", "Hz", "GHz", "MHz",
    "kHz", "IoT", "AI", "ML", "3GPP", "NR", "II", "III", "IV", "VI", "VII",
    "VIII", "IX", "XI", "XII", "OK", "TX", "RX", "OFDM", "QPSK", "BPSK", "QAM",
    "MIMO", "SISO", "MISO", "SIMO", "AWGN", "RF", "FFT", "IFFT", "CSI", "PSD",
}
