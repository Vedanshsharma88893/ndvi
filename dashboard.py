import streamlit as st
import ee
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
import pandas as pd
import datetime
import plotly.express as px
import altair as alt

# --- PAGE CONFIG ---
st.set_page_config(layout="wide")
st.title("NDVI Analysis - Team Rocket")

# --- INITIALIZE GEE ---
@st.cache_resource
def init_gee():
    service_account = 'firebase-adminsdk-4l72c@sanzzakbj.iam.gserviceaccount.com'
    credentials = ee.ServiceAccountCredentials(service_account, 'keyjson.json')
    ee.Initialize(credentials)

@st.cache_resource
def init_gee():
    try:
        ee.Initialize(project='sanzzakbj')
        
    except:
        ee.Authenticate()
        ee.Initialize(project='sanzzakbj')
init_gee()

# --- DRAW MAP ---
st.subheader("📍Draw your area of interest")
draw_map = folium.Map(location=[20.2961, 85.8245], zoom_start=6)
Draw(export=True, filename='aoi.geojson').add_to(draw_map)
draw_data = st_folium(draw_map, height=450, width=700)

# --- GET AOI ---
def get_aoi():
    if draw_data and draw_data.get("all_drawings"):
        geom = draw_data["all_drawings"][0]["geometry"]
        if geom and geom.get("coordinates"):
            return ee.Geometry(geom)
    return None

aoi = get_aoi()

if not aoi:
    st.warning("🚨 Please draw an Area of Interest (AOI) on the map above before proceeding.")
    st.stop()  # This stops the script from continuing if AOI is empty

# --- SLIDER FOR YEAR RANGE ---
st.subheader("Choose year range for NDVI trend")
years = list(range(2000, datetime.datetime.now().year))
year_range = st.slider("Year range", min_value=2000, max_value=years[-1], value=(2010, 2023))

# --- FETCH NDVI DATA ---
def get_ndvi_data(aoi, start_year, end_year):
    def yearly_mean(year):
        start = ee.Date.fromYMD(year, 1, 1)
        end = start.advance(1, 'year')
        img = ee.ImageCollection("MODIS/006/MOD13Q1") \
                .filterBounds(aoi) \
                .filterDate(start, end) \
                .select('NDVI') \
                .mean() \
                .set('year', year)
        return img

    years = list(range(start_year, end_year + 1))
    ndvi_imgs = ee.ImageCollection(ee.List([yearly_mean(y) for y in years]))

    # Reduce each image to mean NDVI
    def img_to_feat(img):
        stats = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=250,
            maxPixels=1e9
        )
        return ee.Feature(None, {'year': img.get('year'), 'NDVI': stats.get('NDVI')})

    fc = ee.FeatureCollection(ndvi_imgs.map(img_to_feat))
    props = fc.getInfo().get('features', [])
    records = [f['properties'] for f in props if f['properties'].get('NDVI') is not None]
    return pd.DataFrame(records)

# --- BIOMASS & CARBON CALCULATION ---
def estimate_biomass(ndvi):
    biomass = 10000 * ndvi  # basic estimate
    carbon = 0.5 * biomass
    co2 = 3.67 * carbon
    return biomass, carbon, co2

with st.spinner("Fetching NDVI data..."):
    df = get_ndvi_data(aoi, year_range[0], year_range[1])

# --- NDVI CHART ---
if not df.empty:
    df['year'] = pd.to_numeric(df['year'])
    df['NDVI'] = pd.to_numeric(df['NDVI']) / 10000  # Normalize NDVI
    df['Biomass'], df['Carbon'], df['CO2'] = zip(*df['NDVI'].map(estimate_biomass))

    line = alt.Chart(df).mark_line(point=True).encode(
        x='year:O',
        y=alt.Y('NDVI:Q', scale=alt.Scale(domain=[0, 1])),
        tooltip=['year', 'NDVI', 'Biomass', 'Carbon', 'CO2']
    ).properties(width=800, height=400, title="NDVI Trend Over Time")
    st.altair_chart(line, use_container_width=True)

    # --- BIOMASS & CARBON TABLE ---
    st.subheader("Biomass & Carbon Stats")
    st.dataframe(df[['year', 'NDVI', 'Biomass', 'Carbon', 'CO2']])

    # --- NDVI GLOW-UP SLIDER ---
    st.subheader("NDVI Glow-Up Slider")
    selected_year = st.slider("Slide through years", min_value=int(df.year.min()), max_value=int(df.year.max()), value=int(df.year.min()))
    selected_img = ee.ImageCollection("MODIS/006/MOD13Q1") \
        .filterDate(f"{selected_year}-01-01", f"{selected_year}-12-31") \
        .select('NDVI') \
        .mean() \
        .clip(aoi)

    # Visualize NDVI for selected year
    map2 = folium.Map(location=[20.2961, 85.8245], zoom_start=6)
    ndvi_params = {
        'min': 0,
        'max': 9000,
        'palette': ['brown', 'yellowgreen', 'green', 'darkgreen']
    }
    url = selected_img.getMapId(ndvi_params)['tile_fetcher'].url_format
    folium.raster_layers.TileLayer(
        tiles=url,
        attr='MODIS NDVI',
        name=f"NDVI {selected_year}",
        overlay=True,
        control=True,
    ).add_to(map2)
    st_folium(map2, height=450, width=700)

# --- EXPORT GIF URL ---
st.subheader("Download NDVI Glow-Up Image")
try:
    gif_url = selected_img.getThumbURL({
        'dimensions': 500,
        'region': aoi,
        'format': 'png',
        'min': 0,
        'max': 9000,
        'palette': ['beige', 'yellowgreen', 'green', 'darkgreen']
    })
    st.markdown(f"[Click here to download NDVI image for {selected_year} ]({gif_url})")
except Exception as e:
    st.error("Oops! Couldn't generate image. Try redrawing your AOI. ")
    st.exception(e)
