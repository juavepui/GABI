"""Entry point of the small/mid-cap feasibility study (#44) for `gabi_cli research smallmid-feasibility`.

Explicit command: it reads SEC frames and the local archive and writes docs/smallmid-feasibility;
``sample`` also downloads SEC submissions. The study stays in the old module because
``smallmid_test`` (the preregistered #44 test) imports it.
"""


def run(sample: bool) -> dict:
    from gabi import factor_stability as fs
    from gabi import smallmid_feasibility

    return fs._json_safe(smallmid_feasibility.run(sample=sample))
