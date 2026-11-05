import os
import sys
import glob
import time

sys.path.insert(0, "src")
from llm import analyze
from validate import clean_result

resume = open("testdata/resume.txt").read()

for path in sorted(glob.glob("testdata/jd*.txt")):
    jd = open(path).read()
    raw, provider = analyze(
        os.environ["GEMINI_API_KEY"],
        os.environ["GROQ_API_KEY"],
        resume,
        jd,
    )
    result = clean_result(raw)
    print("=" * 60)
    print(path, "| provider:", provider, "| score:", result["score"])
    print("matched:", ", ".join(result["matched_skills"]))
    print("missing:", ", ".join(result["missing_skills"]))
    for s in result["suggestions"]:
        print(" -", s)
    time.sleep(5)