"""Two-phase hybrid stepper motor: torque constant, rotor teeth and static load angle.

Model (Kenjo, *Stepping Motors and Their Microprocessor Controls*, 2nd ed., ch. 4; Acarnley,
*Stepping Motors: a guide to theory and practice*, 4th ed., ch. 3), with N rotor teeth,
mechanical angle θ and phase currents i_a, i_b:

    e_a = -K ω sin(Nθ)        e_b = K ω cos(Nθ)
    T   = -K i_a sin(Nθ) + K i_b cos(Nθ) - T_det sin(4Nθ)

A full step moves the electrical angle Nθ by 90°, so step angle = 90°/N (1,8° → N = 50).
With i_a = I cos θ_e and i_b = I sin θ_e (the driver's current vector), T = K I sin(θ_e − Nθ):
the rotor sits at Nθ = θ_e and, under a load torque T_L, lags by asin(T_L / (K I)) / N.

Premise for the datasheet: the holding torque is measured with both phases at the rated
current (two-phase-on, as the step motor tables state "2 phases energized"), so the current
vector has magnitude √2 I and T_hold = √2 K I → K = T_hold / (√2 I).
"""

from __future__ import annotations

import math


def rotor_teeth(step_angle_deg: float) -> float:
    return 90.0 / step_angle_deg


def torque_constant(t_hold: float, i_phase: float) -> float:
    """K in N·m/A (also V·s/rad) from the holding torque at rated current, both phases on."""
    return t_hold / (math.sqrt(2) * i_phase)


def load_angle_deg(t_load: float, k: float, i_vector: float, step_angle_deg: float) -> float:
    """Static lag of the rotor (mechanical degrees) under a load torque, current vector I."""
    ratio = t_load / (k * i_vector)
    if abs(ratio) > 1:
        raise ValueError("torque de carga acima do torque de retenção: o motor perde passo")
    return math.degrees(math.asin(ratio)) / rotor_teeth(step_angle_deg)
