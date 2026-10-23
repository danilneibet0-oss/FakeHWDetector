import argparse
import sys
from pathlib import Path

from . import __version__, branding, i18n
from .kb import updater
from .report.md_export import render_markdown
from .rules.engine import RuleLoadError, load_rules
from .scan import COLLECTORS, assess, build_collectors, collect
from .settings import Settings


def _scan(args) -> int:
    only = [x.strip() for x in args.only.split(",") if x.strip()] if args.only else None
    unknown = [x for x in only or [] if x not in COLLECTORS]
    if unknown:
        print(i18n.t("cli.unknown_collector", names=", ".join(unknown)), file=sys.stderr)
        return 2
    devices = collect(build_collectors(only, args.include_serials, args.enable_spd))
    try:
        rules = load_rules(args.rules_dir)
    except RuleLoadError as e:
        print(i18n.t("cli.rules_error", error=e), file=sys.stderr)
        return 1
    report = assess(devices, rules, lang=i18n.get_language())
    text = render_markdown(report, i18n.get_language()).rstrip("\n") if args.format == "md" else report.to_json()
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=branding.CLI_NAME, description=f"{branding.APP_NAME} - {branding.TAGLINE}")
    p.add_argument("--version", action="version", version=f"{branding.APP_NAME} {__version__}")
    p.add_argument("--lang", choices=i18n.SUPPORTED_LANGUAGES, help="interface language (overrides saved setting)")
    sub = p.add_subparsers(dest="command")
    sc = sub.add_parser("scan", help="collect hardware info and print a normalised JSON report")
    sc.add_argument("--only", default=None, help=f"comma-separated subset of: {','.join(COLLECTORS)}")
    sc.add_argument("--include-serials", action="store_true", help="do not hash serial numbers")
    sc.add_argument("--enable-spd", action="store_true", help="enable the optional SPD plugin (off by default)")
    sc.add_argument("--rules-dir", type=Path, default=None, help="rules directory (default: built-in)")
    sc.add_argument("--format", choices=("json", "md"), default="json", help="report format (default: json)")
    sc.add_argument("-o", "--output", type=Path, default=None, help="write the report to a file instead of stdout")
    r = sub.add_parser("rules", help="list loaded detection rules")
    r.add_argument("--dir", type=Path, default=None, help="rules directory (default: built-in)")
    c = sub.add_parser("config", help="change persistent settings")
    c.add_argument("--language", choices=i18n.SUPPORTED_LANGUAGES, required=True)
    sub.add_parser("selftest", help="check that the bundled data files load")
    sub.add_parser("gui", help="open the graphical interface (needs the [ui] extra)")
    kb = sub.add_parser("kb", help="manage the pci.ids / usb.ids knowledge bases")
    kb_sub = kb.add_subparsers(dest="kb_command", required=True)
    kb_sub.add_parser("status", help="show active database versions and origin")
    ku = kb_sub.add_parser("update", help="download fresh databases (network; explicit command only)")
    ku.add_argument("--only", choices=list(updater.SOURCES), default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    i18n.set_language(args.lang or Settings.load().language)

    if args.command == "scan":
        return _scan(args)
    if args.command == "rules":
        try:
            rules = load_rules(args.dir)
        except RuleLoadError as e:
            print(i18n.t("cli.rules_error", error=e), file=sys.stderr)
            return 1
        print(i18n.t("cli.rules_header", count=len(rules)))
        for rule in rules:
            print(f"  {rule.id}  ({rule.false_positive_risk})")
        return 0
    if args.command == "config":
        Settings.update(language=args.language)
        i18n.set_language(args.language)
        print(i18n.t("cli.language_saved", language=args.language))
        return 0
    if args.command == "kb":
        return _kb(args)
    if args.command == "gui":
        return _gui()
    if args.command == "selftest":
        from . import selftest

        return selftest.run()
    _build_parser().print_help()
    return 0


def _gui() -> int:
    try:
        from .ui import app
    except ImportError:
        print(i18n.t("cli.gui_missing"), file=sys.stderr)
        return 1
    return app.run()


def _kb(args) -> int:
    store = updater.KbStore()
    if args.kb_command == "status":
        for kind, st in store.status().items():
            print(i18n.t("cli.kb_line", kind=kind, version=st["version"], origin=st["origin"], source=st["source_url"] or ""))
        return 0
    rc = 0
    for kind in [args.only] if args.only else list(updater.SOURCES):
        try:
            meta = store.update(kind)
        except updater.KbUpdateError as e:
            print(i18n.t("cli.kb_update_error", kind=kind, error=e), file=sys.stderr)
            rc = 1
        else:
            print(i18n.t("cli.kb_updated", kind=kind, version=meta["version"]))
    return rc


if __name__ == "__main__":
    sys.exit(main())
