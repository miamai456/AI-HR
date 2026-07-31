from pathlib import Path

source = Path(__file__).with_name("首页.py").read_text(encoding="utf-8")
exec(compile(source, "app/首页.py", "exec"))
