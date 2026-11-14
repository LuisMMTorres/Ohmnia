"""GT-PN-02: intrinsic carrier concentration of silicon at 300 K.

Source: Sedra & Smith, Microelectronic Circuits, semiconductor chapter: with B = 7,3·10¹⁵
cm⁻³·K⁻³ᐟ² and Eg = 1,12 eV the book gives ni ≈ 1,5·10¹⁰ cm⁻³ at T = 300 K. Edition, page and
equation number to be confirmed with the printed book (decision D6). Tolerance 2 % (the book
rounds to two significant figures).

GT-PN-01 (depletion width × VR from a worked example) waits for the example chosen by the user
(D6); the formula is covered by tests/unit/devices/test_pn.py with an independent calculation.
"""

import pytest

from circuitos.core.units import q
from circuitos.devices.pn import SILICON, intrinsic_concentration


def test_gt_pn_02_ni_silicon_300k():
    ni = intrinsic_concentration(SILICON, q(300, "K")).value.m_as("1/cm**3")
    assert ni == pytest.approx(1.5e10, rel=0.02)
