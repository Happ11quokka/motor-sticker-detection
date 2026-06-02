import sys
from pathlib import Path

# student_template 디렉토리를 sys.path 에 추가 → `import showcase` 가능
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
