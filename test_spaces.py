import os
import sys
import time
import unicodedata

sys.path.insert(0, "src")
from gemini import call_gemini

resume = open("testdata/resume.txt").read()

for name in ["jd2", "jd5", "jd6"]:
    jd = open(f"testdata/{name}.txt").read()
    raw = call_gemini(os.environ["GEMINI_API_KEY"], resume, jd)
    for s in raw["suggestions"]:
        odd = {c: unicodedata.name(c, "?") for c in s if ord(c) > 126 or ord(c) < 32}
        if odd:
            print(name, "odd characters:", odd)
        for word in ["orapplication", "relationshipmanagement", "pricingmodels"]:
            if word in s:
                print(name, "found:", word)
    time.sleep(5)
print("done")