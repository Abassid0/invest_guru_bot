"""
Add expanded stock coverage to the NGX database.
Adds 45+ new stocks across 11 sectors beyond the original 21.
Run once: python scripts/add_all_stocks.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import create_database_engine, get_session, Company

NEW_STOCKS = [
    # Banking
    {"ticker": "FCMB", "name": "FCMB Group Plc", "sector": "Banking", "market_cap_category": "Mid"},
    {"ticker": "STERLINGNG", "name": "Sterling Financial Holdings", "sector": "Banking", "market_cap_category": "Mid"},
    {"ticker": "UNITYBNK", "name": "Unity Bank Plc", "sector": "Banking", "market_cap_category": "Small"},
    {"ticker": "JAIZBANK", "name": "Jaiz Bank Plc", "sector": "Banking", "market_cap_category": "Small"},
    {"ticker": "WEMABANK", "name": "Wema Bank Plc", "sector": "Banking", "market_cap_category": "Mid"},

    # Insurance
    {"ticker": "MANSARD", "name": "AXA Mansard Insurance", "sector": "Insurance", "market_cap_category": "Mid"},
    {"ticker": "CUSTODIAN", "name": "Custodian Investment Plc", "sector": "Insurance", "market_cap_category": "Mid"},
    {"ticker": "AIICO", "name": "AIICO Insurance Plc", "sector": "Insurance", "market_cap_category": "Mid"},
    {"ticker": "NEM", "name": "NEM Insurance Plc", "sector": "Insurance", "market_cap_category": "Mid"},
    {"ticker": "LASACO", "name": "LASACO Assurance Plc", "sector": "Insurance", "market_cap_category": "Small"},
    {"ticker": "CORNERST", "name": "Cornerstone Insurance Plc", "sector": "Insurance", "market_cap_category": "Small"},

    # FMCG
    {"ticker": "GUINNESS", "name": "Guinness Nigeria Plc", "sector": "FMCG", "market_cap_category": "Large"},
    {"ticker": "NB", "name": "Nigerian Breweries Plc", "sector": "FMCG", "market_cap_category": "Large"},
    {"ticker": "INTBREW", "name": "International Breweries Plc", "sector": "FMCG", "market_cap_category": "Mid"},
    {"ticker": "VITAFOAM", "name": "Vitafoam Nigeria Plc", "sector": "FMCG", "market_cap_category": "Mid"},
    {"ticker": "PZ", "name": "PZ Cussons Nigeria Plc", "sector": "FMCG", "market_cap_category": "Mid"},
    {"ticker": "CADBURY", "name": "Cadbury Nigeria Plc", "sector": "FMCG", "market_cap_category": "Mid"},
    {"ticker": "HONYFLOUR", "name": "Honeywell Flour Mills Plc", "sector": "FMCG", "market_cap_category": "Mid"},

    # Construction / Building Materials
    {"ticker": "BERGER", "name": "Berger Paints Nigeria Plc", "sector": "Construction", "market_cap_category": "Small"},
    {"ticker": "CUTIX", "name": "Cutix Plc", "sector": "Construction", "market_cap_category": "Small"},

    # Conglomerates
    {"ticker": "JOHNHOLT", "name": "John Holt Plc", "sector": "Conglomerate", "market_cap_category": "Small"},
    {"ticker": "BUAFOODS", "name": "BUA Foods Plc", "sector": "Conglomerate", "market_cap_category": "Large"},

    # Agriculture
    {"ticker": "LIVESTOCK", "name": "Livestock Feeds Plc", "sector": "Agriculture", "market_cap_category": "Small"},
    {"ticker": "ELLAH", "name": "Ellah Lakes Plc", "sector": "Agriculture", "market_cap_category": "Small"},
    {"ticker": "OKOMUOIL", "name": "Okomu Oil Palm Plc", "sector": "Agriculture", "market_cap_category": "Mid"},

    # Oil & Gas
    {"ticker": "CONOIL", "name": "Conoil Plc", "sector": "Oil & Gas", "market_cap_category": "Mid"},
    {"ticker": "ARDOVA", "name": "Ardova Plc", "sector": "Oil & Gas", "market_cap_category": "Mid"},
    {"ticker": "TOTALENERG", "name": "TotalEnergies Marketing Nigeria", "sector": "Oil & Gas", "market_cap_category": "Large"},
    {"ticker": "ETERNA", "name": "Eterna Plc", "sector": "Oil & Gas", "market_cap_category": "Small"},
    {"ticker": "MRS", "name": "MRS Oil Nigeria Plc", "sector": "Oil & Gas", "market_cap_category": "Small"},

    # Industrial / Manufacturing
    {"ticker": "WAPCO", "name": "Lafarge Africa Plc", "sector": "Industrial", "market_cap_category": "Large"},
    {"ticker": "MEYER", "name": "Meyer Plc", "sector": "Industrial", "market_cap_category": "Small"},

    # Technology
    {"ticker": "CHAMS", "name": "Chams Holding Company", "sector": "Technology", "market_cap_category": "Small"},
    {"ticker": "OMATEK", "name": "Omatek Ventures Plc", "sector": "Technology", "market_cap_category": "Small"},
    {"ticker": "COURTVILLE", "name": "Courteville Business Solutions", "sector": "Technology", "market_cap_category": "Small"},
    {"ticker": "CWG", "name": "CWG Plc", "sector": "Technology", "market_cap_category": "Small"},

    # Hospitality / Healthcare / Real Estate / Power
    {"ticker": "TRANSCORP", "name": "Transcorp Hotels Plc", "sector": "Hospitality", "market_cap_category": "Mid"},
    {"ticker": "FIDSON", "name": "Fidson Healthcare Plc", "sector": "Healthcare", "market_cap_category": "Mid"},
    {"ticker": "GLAXOSMITH", "name": "GlaxoSmithKline Consumer Nigeria", "sector": "Healthcare", "market_cap_category": "Mid"},
    {"ticker": "NEIMETH", "name": "Neimeth International Pharmaceuticals", "sector": "Healthcare", "market_cap_category": "Small"},
    {"ticker": "UPDC", "name": "UPDC Plc", "sector": "Real Estate", "market_cap_category": "Small"},
    {"ticker": "GEREGU", "name": "Geregu Power Plc", "sector": "Power", "market_cap_category": "Large"},
]


def add_stocks():
    engine = create_database_engine()
    session = get_session(engine)

    added = 0
    skipped = 0

    try:
        for stock in NEW_STOCKS:
            existing = session.query(Company).filter_by(ticker=stock["ticker"]).first()
            if existing:
                skipped += 1
                continue

            company = Company(
                ticker=stock["ticker"],
                name=stock["name"],
                sector=stock["sector"],
                market_cap_category=stock["market_cap_category"],
                is_active=True,
            )
            session.add(company)
            added += 1

        session.commit()
        print(f"Done: {added} stocks added, {skipped} already existed.")
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    add_stocks()
