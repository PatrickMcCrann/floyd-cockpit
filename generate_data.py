"""Generate synthetic financial data for Copperline, a fictional Series B B2B SaaS company.
All data is synthetic. No real company data is used.
Run: python generate_data.py  ->  writes 3 CSVs into ./data/
"""
import csv, os

os.makedirs("data", exist_ok=True)

MONTHS = ["2026-01","2026-02","2026-03","2026-04","2026-05","2026-06","2026-07","2026-08"]

# --- Monthly actuals, Jan-Aug 2026 -----------------------------------------
# Trajectory: ARR $10.2M (Jan) -> $12.1M (Aug), ~40% YoY pace. MRR in $.
# Core tier: ~$1,500/mo avg. Enterprise tier: ~$6,500/mo avg.
core_customers  = [392, 398, 405, 409, 414, 417, 420, 424]
ent_customers   = [46, 47, 49, 50, 52, 53, 54, 55]
core_arpu       = [1480, 1485, 1490, 1495, 1500, 1505, 1510, 1515]
ent_arpu        = [6350, 6380, 6420, 6450, 6480, 6500, 6520, 6550]
new_logos       = [14, 12, 15, 11, 13, 10, 11, 12]
churned_logos   = [6, 6, 8, 7, 8, 7, 8, 8]

headcount       = [64, 65, 66, 67, 68, 69, 70, 70]
payroll         = [962000, 975000, 989000, 1002000, 1015000, 1028000, 1042000, 1048000]
hosting         = [74000, 75000, 77000, 78000, 80000, 81000, 82000, 83000]
software_tools  = [43000, 44000, 44000, 45000, 46000, 46000, 47000, 47000]
marketing_prog  = [118000, 105000, 132000, 110000, 121000, 98000, 115000, 124000]
travel_events   = [22000, 18000, 41000, 19000, 24000, 52000, 20000, 23000]
office_ga       = [58000, 58000, 59000, 59000, 60000, 60000, 61000, 61000]
prof_services   = [28000, 24000, 35000, 26000, 27000, 44000, 26000, 29000]
interest_exp    = [36700] * 8        # $4.0M venture term loan @ 11%
cash_balance    = [11950000, 11520000, 11020000, 10610000, 10160000, 9640000, 9180000, 8700000]
deferred_rev    = [2450000, 2510000, 2580000, 2620000, 2690000, 2730000, 2760000, 2810000]
accounts_recv   = [1310000, 1290000, 1380000, 1340000, 1410000, 1370000, 1430000, 1460000]

with open("data/copperline_actuals.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["month","core_customers","enterprise_customers","core_arpu_usd","enterprise_arpu_usd",
                "mrr_usd","arr_usd","new_logos","churned_logos","headcount","payroll_usd","hosting_usd",
                "software_tools_usd","marketing_programs_usd","travel_events_usd","office_ga_usd",
                "prof_services_usd","interest_expense_usd","total_opex_usd","net_burn_usd",
                "cash_balance_usd","deferred_revenue_usd","accounts_receivable_usd"])
    for i, m in enumerate(MONTHS):
        mrr = core_customers[i]*core_arpu[i] + ent_customers[i]*ent_arpu[i]
        opex = (payroll[i]+hosting[i]+software_tools[i]+marketing_prog[i]+travel_events[i]
                +office_ga[i]+prof_services[i]+interest_exp[i])
        burn = opex - mrr  # simplified: cash collections approximated by MRR
        w.writerow([m, core_customers[i], ent_customers[i], core_arpu[i], ent_arpu[i],
                    mrr, mrr*12, new_logos[i], churned_logos[i], headcount[i], payroll[i],
                    hosting[i], software_tools[i], marketing_prog[i], travel_events[i],
                    office_ga[i], prof_services[i], interest_exp[i], opex, burn,
                    cash_balance[i], deferred_rev[i], accounts_recv[i]])

# --- Planning assumptions (the levers + fixed facts) ------------------------
rows = [
    # name, value, unit, editable, note
    ["fiscal_year_end","2026-12-31","date","no","Calendar fiscal year"],
    ["fy26_arr_target",13500000,"usd","no","Board plan: exit FY26 at $13.5M ARR"],
    ["fy27_arr_target",18000000,"usd","no","Board plan: exit FY27 at $18M ARR (~49% growth)"],
    ["min_cash_covenant",3000000,"usd","no","Venture debt covenant: cash never below $3.0M"],
    ["debt_drawn",4000000,"usd","no","Term loan drawn; 11% interest, interest-only through 2027"],
    ["debt_available",500000,"usd","no","Undrawn capacity on the venture debt line"],
    ["monthly_logo_churn_pct",1.8,"percent","yes","Blended logo churn per month (LEVER)"],
    ["net_revenue_retention_pct",105,"percent","yes","NRR annualized (LEVER)"],
    ["new_logos_per_month",12,"count","yes","Current organic acquisition pace (LEVER)"],
    ["price_increase_pct",0,"percent","yes","Price increase at renewal, effective Oct 1 (LEVER)"],
    ["new_ae_hires",4,"count","yes","Planned AE hires for the Q4 bookings ramp (LEVER)"],
    ["new_ae_start_date","2026-12-01","date","yes","AE start date in current plan (LEVER) -- see conflict"],
    ["ae_ramp_months",3,"months","no","Months before a new AE reaches full productivity"],
    ["ae_quota_net_new_mrr",22000,"usd_per_month","no","Net-new MRR per fully ramped AE per month"],
    ["q4_net_new_mrr_required",350000,"usd","no","Net-new MRR needed in Q4 to stay on the FY27 ramp"],
    ["loaded_cost_per_ae",16500,"usd_per_month","no","Fully loaded monthly cost per AE"],
    ["merit_increase_jan27_pct",4,"percent","no","Company-wide merit increase effective Jan 2027"],
    ["enterprise_renewals_at_risk_mrr",42000,"usd","no","Two enterprise logos flagged at-risk for Nov renewal"],
]
with open("data/copperline_assumptions.csv","w",newline="") as f:
    w = csv.writer(f)
    w.writerow(["assumption","value","unit","editable_lever","note"])
    w.writerows(rows)

# --- Acquisition target profile --------------------------------------------
rows = [
    ["target_name","Brightpath Software","","Fictional smaller competitor, same category"],
    ["arr_usd",3200000,"usd","Trailing ARR"],
    ["asking_price_usd",7500000,"usd","~2.3x ARR, seller expects mostly cash"],
    ["gross_retention_pct",85,"percent","Weaker than Copperline's; churn risk in migration"],
    ["monthly_opex_usd",180000,"usd","Target's current run-rate opex"],
    ["headcount",14,"count","Team acquired; 3 likely redundant roles"],
    ["integration_cost_usd",400000,"usd","One-time, spread over first 6 months post-close"],
    ["expected_close","2026-11-01","date","If pursued, closes Nov 1"],
    ["revenue_synergy_note","Cross-sell est. +$25k net-new MRR/mo from month 7","",""],
]
with open("data/copperline_acquisition_target.csv","w",newline="") as f:
    w = csv.writer(f)
    w.writerow(["field","value","unit","note"])
    w.writerows(rows)

print("Wrote data/copperline_actuals.csv, copperline_assumptions.csv, copperline_acquisition_target.csv")
