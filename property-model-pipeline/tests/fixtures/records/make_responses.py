"""Recorded-style ArcGIS / NOAA / FEMA replies for the records and hazards tests.

    python3 make_responses.py          # rewrites responses/*.json|csv|html next to this file

Real field names (copied from the public layers' ?f=json, 2026-11-25), invented values, and an invented place
in the open Pacific (lat 10, lon -140): no real address, parcel, coordinate or person. Some replies carry
fields that were NOT requested (OWNNAME1, MRTNM1, contractor_name, SELLERS_NAME ...), as a misbehaving server
might: the tests check that none of them reaches a written file.

Local layout (metres east / north of the origin):
    subject parcel  x -10..10, y -15..15      neighbour parcel x 10..30 (shares the east line)
    subject house   x -6..6,   y -5..7        neighbour house  x 14..26, y -5..7
    permits         subject (1, 2) x3, neighbour (20, 0)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from propmodel.geo import LocalFrame  # noqa: E402

LAT0, LON0 = 10.0, -140.0
FR = LocalFrame(LAT0, LON0)
OUT = os.path.join(HERE, "responses")
MS = 86400000


def ll(x, y):
    lat, lon, _ = FR.to_geodetic(x, y, 0.0)
    return [round(float(lon), 8), round(float(lat), 8)]


def rect(x0, y0, x1, y1, d=0.0):
    """ArcGIS ring (clockwise) for a rectangle, optionally shifted by d metres east."""
    pts = [(x0 + d, y0), (x0 + d, y1), (x1 + d, y1), (x1 + d, y0), (x0 + d, y0)]
    return {"rings": [[ll(x, y) for x, y in pts]], "spatialReference": {"wkid": 4326}}


def pt(x, y):
    lon, lat = ll(x, y)
    return {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}


def epoch(y, m, d):
    import datetime as dt
    return int(dt.datetime(y, m, d, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)


def fs(features, fields):
    return {"displayFieldName": "", "fieldAliases": {f: f for f in fields},
            "fields": [{"name": f, "type": "esriFieldTypeString"} for f in fields], "features": features}

HEADER = ("BEGIN_YEARMONTH,BEGIN_DAY,BEGIN_TIME,END_YEARMONTH,END_DAY,END_TIME,EPISODE_ID,EVENT_ID,STATE,STATE_FIPS,YEAR,"
          "MONTH_NAME,EVENT_TYPE,CZ_TYPE,CZ_FIPS,CZ_NAME,WFO,BEGIN_DATE_TIME,CZ_TIMEZONE,END_DATE_TIME,INJURIES_DIRECT,"
          "INJURIES_INDIRECT,DEATHS_DIRECT,DEATHS_INDIRECT,DAMAGE_PROPERTY,DAMAGE_CROPS,SOURCE,MAGNITUDE,MAGNITUDE_TYPE,"
          "FLOOD_CAUSE,CATEGORY,TOR_F_SCALE,TOR_LENGTH,TOR_WIDTH,TOR_OTHER_WFO,TOR_OTHER_CZ_STATE,TOR_OTHER_CZ_FIPS,"
          "TOR_OTHER_CZ_NAME,BEGIN_RANGE,BEGIN_AZIMUTH,BEGIN_LOCATION,END_RANGE,END_AZIMUTH,END_LOCATION,BEGIN_LAT,"
          "BEGIN_LON,END_LAT,END_LON,EPISODE_NARRATIVE,EVENT_NARRATIVE,DATA_SOURCE")


def storm_csv():
    """Synthetic NCEI Storm Events rows (real columns). Distances from the origin are in the comments."""
    import csv
    import io
    cols = HEADER.split(",")
    rows = [
        # date, type, magnitude, mag type, F scale, (x, y) begin, (x, y) end
        ("2016-03-01", "Hail", "1.00", "", "", (0, 320), None),          # 0.2 mi, before the 10-year window
        ("2016-12-01", "Hail", "1.00", "", "", (0, -1450), None),        # 0.9 mi
        ("2017-07-04", "Hail", "1.75", "", "", (4828, 0), None),         # 3 mi E
        ("2018-05-30", "Tornado", "", "", "EF1", (19312, 0), (1287, 0)),  # track ends 0.8 mi E
        ("2019-06-20", "Hail", "2.00", "", "", (24140, 0), None),        # 15 mi: outside 10 mi
        ("2020-01-10", "Heavy Snow", "", "", "", None, None),            # zone event, no point
        ("2021-05-05", "Thunderstorm Wind", "50", "MG", "", (-12875, 0), None),   # 8 mi W, 57.5 mph
        ("2022-08-01", "Thunderstorm Wind", "61", "EG", "", (0, -3219), None),    # 2 mi S, 70 mph
        ("2023-06-10", "Hail", "1.25", "", "", (0, 800), None),          # 0.5 mi N
        ("2026-05-20", "Hail", "0.75", "", "", (500000, 0), None),       # far away: sets the file's last date
    ]
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for i, (d, et, mag, mt, fsc, b, e) in enumerate(rows):
        y, m, dd = d.split("-")
        r = {c: "" for c in cols}
        r.update(BEGIN_YEARMONTH=y + m, BEGIN_DAY=str(int(dd)), BEGIN_TIME="1730", END_YEARMONTH=y + m,
                 END_DAY=str(int(dd)), END_TIME="1745", EPISODE_ID=str(900000 + i), EVENT_ID=str(9000000 + i),
                 STATE="TESTLAND", STATE_FIPS="99", YEAR=y, MONTH_NAME="June", EVENT_TYPE=et,
                 CZ_TYPE="C" if b else "Z", CZ_FIPS="999", CZ_NAME="ALPHA", WFO="XXX", CZ_TIMEZONE="CST-6",
                 DAMAGE_PROPERTY="0.00K", DAMAGE_CROPS="0.00K", SOURCE="Trained Spotter", MAGNITUDE=mag,
                 MAGNITUDE_TYPE=mt, TOR_F_SCALE=fsc, BEGIN_RANGE="1", BEGIN_AZIMUTH="N", BEGIN_LOCATION="TESTVILLE",
                 EPISODE_NARRATIVE="PLANTED EPISODE NARRATIVE naming a PLANTED PERSON and a street.",
                 EVENT_NARRATIVE="PLANTED EVENT NARRATIVE: a PLANTED PERSON reported it from home.", DATA_SOURCE="CSV")
        if b:
            r["BEGIN_LON"], r["BEGIN_LAT"] = [str(v) for v in ll(*b)]
            r["END_LON"], r["END_LAT"] = [str(v) for v in ll(*(e or b))]
        w.writerow([r[c] for c in cols])
    return out.getvalue()


def main():
    os.makedirs(OUT, exist_ok=True)
    R = {}
    R["address_points"] = fs([
        {"attributes": {"OBJECTID": 11, "TAG": "T0000001", "ADDRESS": "1 TEST AVE", "LAT": LAT0, "LON": LON0,
                        "MUNICIPALITY": "TESTVILLE", "COUNTY": "Alpha", "YEARBUILT": "1978", "OCCUPANCY": "Single Family",
                        "CONSTRTYPE": "Wood Frame", "CORNERLOT": "No"}, "geometry": pt(0, 0)}],
        ["OBJECTID", "TAG", "ADDRESS", "LAT", "LON", "MUNICIPALITY", "COUNTY", "YEARBUILT"])
    R["parcels"] = fs([
        {"attributes": {"OBJECTID": 21, "TAG": "T0000001", "ADDRESS": "1 TEST AVE", "ADDITION": "EXAMPLE ADDN",
                        "ACREAGE": 0.1483, "SQFT": 6458.0, "LEGAL": "LOT 1 BLK 1 EXAMPLE ADDN",
                        "ACTIVITY": "11 - Single-Family", "LANDUSE": 11, "NUMUNITS": 1, "COUNTY": "ALPHA",
                        "COUNTYID": "C-0000001", "PARCELTYPE": "Standard Tax Parcel",
                        "OWNNAME1": "PLANTED NAME ONE", "OWNADDRESS": "PLANTED MAIL ADDRESS"},
         "geometry": rect(-10, -15, 10, 15)}],
        ["OBJECTID", "TAG", "ADDRESS", "ACREAGE", "SQFT", "COUNTY", "OWNNAME1"])
    R["parcels_neighbour"] = fs([
        {"attributes": {"OBJECTID": 22, "TAG": "T0000002", "ADDRESS": "3 TEST AVE", "ACREAGE": 0.1483, "SQFT": 6458.0,
                        "COUNTY": "ALPHA", "COUNTYID": "C-0000002"}, "geometry": rect(10, -15, 30, 15)}],
        ["OBJECTID", "TAG"])
    R["footprints"] = fs([
        {"attributes": {"OBJECTID": 31, "STRUCTURE": 110, "NUMBERSTORIES": 1, "GROUNDELEVATION": 1500.2,
                        "BUILDINGTOPELEVATION": 1522.8, "CAPTUREMETH": "Consultant Deliverable", "OWNEDBY": -1},
         "geometry": rect(-6, -5, 6, 7)},
        {"attributes": {"OBJECTID": 32, "STRUCTURE": 110, "NUMBERSTORIES": 2, "OWNEDBY": -1},
         "geometry": rect(14, -5, 26, 7)}],
        ["OBJECTID", "STRUCTURE", "NUMBERSTORIES", "OWNEDBY"])
    R["permits"] = fs([
        {"attributes": {"OBJECTID": 41, "MAINADDRESS": "1 TEST AVE", "PERMITNUMBER": "RES-19-0001",
                        "PERMITTYPE": "Residential Building", "PERMITSTATUS": "Finaled", "WORKCLASS": "Reshingle",
                        "APPLYDATE": epoch(2019, 5, 20), "ISSUEDATE": epoch(2019, 5, 21), "FINALIZEDATE": epoch(2019, 6, 12),
                        "VALUATION": 9800.0, "contractor_name": "PLANTED CONTRACTOR LLC"}, "geometry": pt(1, 2)},
        {"attributes": {"OBJECTID": 42, "MAINADDRESS": "1 TEST AVE", "PERMITNUMBER": "RES-17-0002",
                        "PERMITTYPE": "Residential Building", "PERMITSTATUS": "Finaled", "WORKCLASS": "Deck",
                        "APPLYDATE": epoch(2017, 4, 2), "ISSUEDATE": epoch(2017, 4, 3), "FINALIZEDATE": epoch(2017, 8, 1),
                        "VALUATION": 4000.0, "contractor_name": "PLANTED BUILDER INC"}, "geometry": pt(1, 2)},
        {"attributes": {"OBJECTID": 43, "MAINADDRESS": "1 TEST AVE", "PERMITNUMBER": "RES-24-0003",
                        "PERMITTYPE": "Residential Building", "PERMITSTATUS": "Expired", "WORKCLASS": "Reshingle",
                        "APPLYDATE": epoch(2024, 7, 1), "ISSUEDATE": epoch(2024, 7, 2), "FINALIZEDATE": None,
                        "VALUATION": 12000.0}, "geometry": pt(1, 2)},
        {"attributes": {"OBJECTID": 44, "MAINADDRESS": "3 TEST AVE", "PERMITNUMBER": "RES-22-0004",
                        "PERMITTYPE": "Residential Building", "PERMITSTATUS": "Finaled", "WORKCLASS": "Addition",
                        "APPLYDATE": epoch(2022, 3, 1), "ISSUEDATE": epoch(2022, 3, 2), "FINALIZEDATE": epoch(2022, 9, 9),
                        "VALUATION": 80000.0}, "geometry": pt(20, 0)}],
        ["OBJECTID", "MAINADDRESS", "PERMITNUMBER", "WORKCLASS", "contractor_name"])
    # county "Alpha" (Minnehaha-style field names)
    R["alpha_assessed"] = fs([
        {"attributes": {"OBJECTID": 51, "TAG": "T0000001", "MRALVL": 0, "MRABVL": 0, "MRNLVL": 61000, "MRNBVL": 238500,
                        "TOTAL": 299500, "TYPE": "Residential", "MRTNM1": "PLANTED TAXPAYER", "MRTADR": "PLANTED MAIL"},
         "geometry": rect(-10, -15, 10, 15, 0.3)},
        {"attributes": {"OBJECTID": 52, "TAG": "T0000002", "MRNLVL": 59000, "MRNBVL": 301000, "TOTAL": 360000,
                        "TYPE": "Residential"}, "geometry": rect(10, -15, 30, 15, 0.3)}],
        ["OBJECTID", "TAG", "MRNLVL", "MRNBVL", "TOTAL", "MRTNM1"])
    R["alpha_quality"] = fs([
        {"attributes": {"OBJECTID": 61, "TAG": "T0000001", "COUNTYID": "C-0000001", "House_desc": "10 Ranch 1st 1970-1979",
                        "Grade": 4, "Grade_desc": "Average", "OWNNAME1": "PLANTED NAME ONE"},
         "geometry": rect(-10, -15, 10, 15, -0.2)}],
        ["OBJECTID", "TAG", "House_desc", "Grade", "OWNNAME1"])
    R["alpha_sales_2025"] = fs([], ["OBJECTID", "TAG", "SALE_DATE", "SALE_PRICE"])
    R["alpha_sales_2023"] = fs([
        {"attributes": {"OBJECTID": 71, "TAG": "T0000001", "INSTR_DATE": epoch(2023, 3, 14), "SELL_PRICE": 289900,
                        "Year_Built": 1978, "CLASS": 1, "House_Desc": "10 Ranch 1st 1970-1979", "Grade": "4",
                        "Condition": "Average", "OWNNAME1": "PLANTED NAME ONE"},
         "geometry": rect(-10, -15, 10, 15)}],
        ["OBJECTID", "TAG", "INSTR_DATE", "SELL_PRICE", "Year_Built"])
    # county "Beta" (Lincoln-style joined / table field names)
    R["beta_parcels"] = fs([
        {"attributes": {"DBO.Parcel.OBJECTID": 81, "DBO.Parcel.PID": "B-000-001", "DBO.Parcel.Zoning": "R1",
                        "DBO.Parcel.SqFtCalc": 6460.4, "DBO.Parcel.AcreCalc": 0.1483, "DBO.GIS_Parcels.Class1": "NA-O",
                        "DBO.GIS_Parcels.Value1": 312000, "DBO.GIS_Parcels.Value2": 0,
                        "DBO.GIS_Parcels.Name": "PLANTED NAME", "DBO.GIS_Parcels.NameADD": "PLANTED NAME 2",
                        "DBO.GIS_Parcels.Add1": "PLANTED MAIL 1"}, "geometry": rect(-10, -15, 10, 15)}],
        ["DBO.Parcel.PID", "DBO.GIS_Parcels.Name"])
    R["beta_permits"] = fs([
        {"attributes": {"OBJECTID": 91, "PID": "B-000-001", "DateApproved": epoch(2021, 9, 30), "Permit": "LC-21-77",
                        "ProjectType": "Large Residential Project", "Type": "Addition", "ProjDesc": "Addition",
                        "ProjectCost": 65000.0, "PropertyOwner": "PLANTED OWNER"}}],
        ["OBJECTID", "PID", "DateApproved", "Type", "PropertyOwner"])
    R["beta_fullsales"] = fs([
        {"attributes": {"OBJECTID": 101, "PARCEL_ID": "B-000-001", "SALE_DATE": 20200817, "SALE_YEAR": 2020,
                        "SALE_PRICE": 275000, "FULLVALUE": 251000, "PROPERTY_CLASS": "NA-O",
                        "SELLERS_NAME": "PLANTED SELLER", "BUYERS_NAME": "PLANTED BUYER"}},
        {"attributes": {"OBJECTID": 102, "PARCEL_ID": "B-000-001", "SALE_DATE": 20110402, "SALE_YEAR": 2011,
                        "SALE_PRICE": 0, "FULLVALUE": 180000, "PROPERTY_CLASS": "NA-O"}}],
        ["OBJECTID", "PARCEL_ID", "SALE_DATE", "SELLERS_NAME"])
    R["nfhl"] = {"fields": [{"name": f} for f in ("FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "STATIC_BFE", "DFIRM_ID")],
                 "features": [{"attributes": {"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD", "SFHA_TF": "F",
                                              "STATIC_BFE": -9999.0, "DFIRM_ID": "99999C"}},
                              {"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T", "STATIC_BFE": 1498.5,
                                              "DFIRM_ID": "99999C"}}]}
    R["iem_lsr"] = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"wfo": "XXX", "type": "H", "magf": 1.5, "typetext": "HAIL", "unit": "Inch",
                                           "valid": "2026-07-15T23:10:00Z", "lat": ll(0, 480)[1], "lon": ll(0, 480)[0],
                                           "city": "1 N Testville", "county": "Alpha", "st": "ZZ", "source": "Trained Spotter",
                                           "qualifier": "E", "remark": "PLANTED REMARK naming a PLANTED PERSON"},
         "geometry": {"type": "Point", "coordinates": ll(0, 480)}},
        {"type": "Feature", "properties": {"wfo": "XXX", "type": "R", "magf": 2.1, "typetext": "RAIN", "unit": "Inch",
                                           "valid": "2026-07-15T23:00:00Z", "lat": LAT0, "lon": LON0, "remark": "x"},
         "geometry": {"type": "Point", "coordinates": [LON0, LAT0]}},
        {"type": "Feature", "properties": {"wfo": "XXX", "type": "G", "magf": 65, "typetext": "TSTM WND GST", "unit": "MPH",
                                           "valid": "2026-08-02T01:30:00Z", "lat": ll(3000, 0)[1], "lon": ll(3000, 0)[0],
                                           "qualifier": "M", "source": "ASOS"},
         "geometry": {"type": "Point", "coordinates": ll(3000, 0)}}]}
    for k, v in R.items():
        with open(os.path.join(OUT, k + ".json"), "w") as f:
            json.dump(v, f, indent=1)
    # SPC daily hail CSV for the report day of the IEM hail (2026-07-15 23:10Z -> SPC day 260715): one duplicate
    # of the IEM report and one extra report 2 miles south
    a, b = ll(30, 470), ll(0, -3220)
    with open(os.path.join(OUT, "spc_260715_hail.csv"), "w") as f:
        f.write("Time,Size,Location,County,State,Lat,Lon,Comments\n")
        f.write(f"2310,150,1 N Testville,Alpha,ZZ,{a[1]:.4f},{a[0]:.4f},PLANTED COMMENT naming a PLANTED PERSON (XXX)\n")
        f.write(f"2320,100,2 S Testville,Alpha,ZZ,{b[1]:.4f},{b[0]:.4f},(XXX)\n")
    with open(os.path.join(OUT, "spc_260715_wind.csv"), "w") as f:
        f.write("Time,Speed,Location,County,State,Lat,Lon,Comments\n")
    # SWDI nx3hail reply for the window around 2026-07-15 and an error reply
    c = ll(200, 300)
    with open(os.path.join(OUT, "swdi_nx3hail.csv"), "w") as f:
        f.write("ZTIME,WSR_ID,CELL_ID,PROB,SEVPROB,MAXSIZE,LAT,LON\n")
        f.write(f"2026-07-15T23:05:12Z,KXXX,A1,100,70,1.75,{c[1]:.3f},{c[0]:.3f}\n")
        f.write(f"2026-07-15T23:09:40Z,KXXX,A1,90,40,1.25,{c[1]:.3f},{c[0]:.3f}\n")
        f.write("\nsummary\ncount,2\n")
    # NCEI directory listing (two rebuilds of 2026: the newest one must be chosen)
    with open(os.path.join(OUT, "stormevents_index.html"), "w") as f:
        f.write("<html><body><pre>\n")
        for y in range(2015, 2027):
            for c_ in ("20260101", "20261119"):
                n = f"StormEvents_details-ftp_v1.0_d{y}_c{c_}.csv.gz"
                f.write(f'<a href="{n}">{n}</a> 01-Jan-2026 00:00 1M\n')
        f.write("</pre></body></html>\n")
    with open(os.path.join(OUT, "storm_events_sample.csv"), "w", newline="") as f:
        f.write(storm_csv())
    print("wrote", len(R) + 6, "files to", OUT)


if __name__ == "__main__":
    main()
