from __future__ import annotations

from messknecht.main import main


def test_main(capsys) -> None:
    """Test that main runs without errors."""
    main()
    captured = capsys.readouterr()
    assert "Hello, World!" in captured.out
