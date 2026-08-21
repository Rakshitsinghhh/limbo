"""
Project Limbo — Bank Configuration Profiles
Defines historical settlement SLA windows, limbo probabilities, delay mean times,
success rates, and failure recovery rates for HDFC, SBI, ICICI, Axis, and Kotak Bank.
"""

BANK_PROFILES = {
    "HDFC": {
        "name": "HDFC Bank",
        "rails": {
            "UPI_AUTOPAY": {"expected_window_sec": 30, "limbo_probability": 0.18, "delay_mean_sec": 120, "success_rate": 0.88},
            "NACH": {"expected_window_sec": 7200, "limbo_probability": 0.25, "delay_mean_sec": 14400, "success_rate": 0.72},
            "CARD": {"expected_window_sec": 15, "limbo_probability": 0.08, "delay_mean_sec": 60, "success_rate": 0.92}
        },
        "retry_budget": {"daily_limit_per_merchant": 120, "hourly_threshold": 20},
        "failure_recovery_rates": {
            "INSUFFICIENT_FUNDS": 0.45,
            "BANK_TIMEOUT": 0.82,
            "RISK_DECLINE": 0.15,
            "NETWORK_ERROR": 0.88
        }
    },
    "SBI": {
        "name": "State Bank of India",
        "rails": {
            "UPI_AUTOPAY": {"expected_window_sec": 45, "limbo_probability": 0.30, "delay_mean_sec": 300, "success_rate": 0.78},
            "NACH": {"expected_window_sec": 14400, "limbo_probability": 0.38, "delay_mean_sec": 28800, "success_rate": 0.65},
            "CARD": {"expected_window_sec": 20, "limbo_probability": 0.14, "delay_mean_sec": 180, "success_rate": 0.84}
        },
        "retry_budget": {"daily_limit_per_merchant": 80, "hourly_threshold": 12},
        "failure_recovery_rates": {
            "INSUFFICIENT_FUNDS": 0.50,
            "BANK_TIMEOUT": 0.75,
            "RISK_DECLINE": 0.10,
            "NETWORK_ERROR": 0.82
        }
    },
    "ICICI": {
        "name": "ICICI Bank",
        "rails": {
            "UPI_AUTOPAY": {"expected_window_sec": 25, "limbo_probability": 0.15, "delay_mean_sec": 90, "success_rate": 0.90},
            "NACH": {"expected_window_sec": 5400, "limbo_probability": 0.20, "delay_mean_sec": 10800, "success_rate": 0.78},
            "CARD": {"expected_window_sec": 12, "limbo_probability": 0.06, "delay_mean_sec": 45, "success_rate": 0.94}
        },
        "retry_budget": {"daily_limit_per_merchant": 150, "hourly_threshold": 25},
        "failure_recovery_rates": {
            "INSUFFICIENT_FUNDS": 0.42,
            "BANK_TIMEOUT": 0.85,
            "RISK_DECLINE": 0.18,
            "NETWORK_ERROR": 0.90
        }
    },
    "AXIS": {
        "name": "Axis Bank",
        "rails": {
            "UPI_AUTOPAY": {"expected_window_sec": 35, "limbo_probability": 0.22, "delay_mean_sec": 150, "success_rate": 0.84},
            "NACH": {"expected_window_sec": 7200, "limbo_probability": 0.28, "delay_mean_sec": 18000, "success_rate": 0.70},
            "CARD": {"expected_window_sec": 18, "limbo_probability": 0.10, "delay_mean_sec": 90, "success_rate": 0.88}
        },
        "retry_budget": {"daily_limit_per_merchant": 100, "hourly_threshold": 15},
        "failure_recovery_rates": {
            "INSUFFICIENT_FUNDS": 0.38,
            "BANK_TIMEOUT": 0.80,
            "RISK_DECLINE": 0.12,
            "NETWORK_ERROR": 0.85
        }
    },
    "KOTAK": {
        "name": "Kotak Mahindra Bank",
        "rails": {
            "UPI_AUTOPAY": {"expected_window_sec": 30, "limbo_probability": 0.20, "delay_mean_sec": 110, "success_rate": 0.86},
            "NACH": {"expected_window_sec": 6000, "limbo_probability": 0.22, "delay_mean_sec": 12000, "success_rate": 0.75},
            "CARD": {"expected_window_sec": 15, "limbo_probability": 0.08, "delay_mean_sec": 60, "success_rate": 0.91}
        },
        "retry_budget": {"daily_limit_per_merchant": 110, "hourly_threshold": 18},
        "failure_recovery_rates": {
            "INSUFFICIENT_FUNDS": 0.40,
            "BANK_TIMEOUT": 0.82,
            "RISK_DECLINE": 0.14,
            "NETWORK_ERROR": 0.87
        }
    }
}
