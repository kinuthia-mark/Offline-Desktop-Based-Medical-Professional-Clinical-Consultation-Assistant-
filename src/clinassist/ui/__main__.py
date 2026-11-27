"""Entry point: `python -m clinassist.ui`, or ClinAssist.exe once installed.

    --check                 run the start-up checks, print them and exit (no window)
    --self-test             use every heavy part once (window, database, speech model...) and exit
    --verify-bundle <dir>   check every file of an offline model bundle and exit

The installer and support staff use these to confirm an installation works.
"""

# This file is the program's front door. The installer and support staff run it with a flag
# to check an install without opening the window. With no flag, it opens the normal app.
import sys

# sys.argv is the list of command-line words. Each flag is handled, then the program exits.
if "--verify-bundle" in sys.argv:
    # Used by the installer before copying anything: every bundled file must be unchanged.
    # Imported only when needed, so the other paths stay quick.
    from clinassist.bundle import verify_bundle

    # The folder name is the word after the flag. Any problems are printed one per line.
    problems = verify_bundle(sys.argv[sys.argv.index("--verify-bundle") + 1])
    print("\n".join(problems) or "bundle_ok")
    # Exit code 1 tells the installer the bundle is bad; 0 means all good.
    raise SystemExit(1 if problems else 0)

if "--self-test" in sys.argv:
    from clinassist.selftest import run

    raise SystemExit(run())

if "--check" in sys.argv:
    from clinassist.startup import main as check

    raise SystemExit(check())

# No flag was given, so start the real app. noqa E402 allows this import below the code.
from clinassist.ui.main import main  # noqa: E402

raise SystemExit(main())
