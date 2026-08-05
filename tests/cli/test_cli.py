"""yq CLI 冒烟测试：入口、帮助、版本、错误处理。"""

from typer.testing import CliRunner

from yq.cli import app

runner = CliRunner()


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "factor" in result.stdout
    assert "cache" in result.stdout


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "yq" in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_unknown_command_fails():
    result = runner.invoke(app, ["bogus"])
    assert result.exit_code != 0


def test_factor_help_lists_subcommands():
    result = runner.invoke(app, ["factor", "--help"])
    assert result.exit_code == 0
    for cmd in ("list", "run", "evaluate"):
        assert cmd in result.stdout


def test_cache_help_lists_subcommands():
    result = runner.invoke(app, ["cache", "--help"])
    assert result.exit_code == 0
    for cmd in ("info", "clear"):
        assert cmd in result.stdout
