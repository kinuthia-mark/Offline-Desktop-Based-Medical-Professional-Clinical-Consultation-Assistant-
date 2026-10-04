"""Entry point: `python -m clinassist.ui`, or ClinAssist.exe once installed.

    --check                 run the start-up checks, print them and exit (no window)
    --verify-bundle <dir>   check every file of an offline model bundle and exit

The installer and support staff use these to confirm an installation works.
"""

import sys

if "--verify-bundle" in sys.argv:
    # Used by the installer before copying anything: every bundled file must be unchanged.
    from clinassist.bundle import verify_bundle

    problems = verify_bundle(sys.argv[sys.argv.index("--verify-bundle") + 1])
    print("\n".join(problems) or "bundle_ok")
    raise SystemExit(1 if problems else 0)

if "--check" in sys.argv:
    from clinassist.startup import main as check

    raise SystemExit(check())

from clinassist.ui.main import main  # noqa: E402

raise SystemExit(main())
