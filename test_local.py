import os
import sys
import json

sys.path.insert(0, "src")
from gemini import call_gemini

resume = """Sarang. B.Tech Electronics and Computer Engineering.
Skills: Python, PyTorch, OpenCV, Docker, Git.
Intern: built an object detection pipeline for a robotics project."""

jd = """ML Engineer. Required: Python, PyTorch, AWS (SageMaker or Lambda),
Docker, SQL, 1+ years experience with model deployment."""

result = call_gemini(os.environ["GEMINI_API_KEY"], resume, jd)
print(json.dumps(result, indent=2))