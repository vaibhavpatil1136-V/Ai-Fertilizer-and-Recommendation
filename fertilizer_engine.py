# fertilizer_engine.py -- Nutrient evaluation and fertilizer engine helpers
"""
Nutrient evaluation logic and helper utilities for fertilizer analysis.
"""

def npk_level(val: float, p33: float, p66: float) -> str:
    """
    Categorize nutrient level into Low, Medium, or High based on percentile thresholds.
    Bug fix: Uses '<=' for the low check instead of '<'.
    When K = 0 and p33 is 0, this correctly returns 'Low' rather than falling into 'Medium'.
    """
    if val <= p33:
        return "Low"
    elif val <= p66:
        return "Medium"
    else:
        return "High"


def evaluate_soil_nutrients(nitrogen: float, phosphorous: float, potassium: float, ref_stats: dict) -> dict:
    """
    Evaluate N, P, K levels against dataset percentile benchmarks.
    Returns status ('Low', 'Medium', 'High') and recommendation notes.
    """
    n_p33 = ref_stats.get("Nitrogen", {}).get("p33", 15.0)
    n_p66 = ref_stats.get("Nitrogen", {}).get("p66", 35.0)
    p_p33 = ref_stats.get("Phosphorous", {}).get("p33", 15.0)
    p_p66 = ref_stats.get("Phosphorous", {}).get("p66", 30.0)
    k_p33 = ref_stats.get("Potassium", {}).get("p33", 0.0)
    k_p66 = ref_stats.get("Potassium", {}).get("p66", 10.0)

    n_status = npk_level(nitrogen, n_p33, n_p66)
    p_status = npk_level(phosphorous, p_p33, p_p66)
    k_status = npk_level(potassium, k_p33, k_p66)

    return {
        "Nitrogen": {"value": nitrogen, "status": n_status, "p33": n_p33, "p66": n_p66},
        "Phosphorous": {"value": phosphorous, "status": p_status, "p33": p_p33, "p66": p_p66},
        "Potassium": {"value": potassium, "status": k_status, "p33": k_p33, "p66": k_p66},
    }
