import streamlit as st
import pandas as pd
import psycopg2
import time
import altair as alt

from sqlalchemy import create_engine

# Database Connection
def get_data():
    try:
        engine = create_engine("postgresql+psycopg2://user:password@localhost:5432/transactions_db")
        query = "SELECT * FROM category_sales ORDER BY window_start DESC LIMIT 100"
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        st.error(f"Error connecting to database: {e}")
        return pd.DataFrame()

st.set_page_config(
    page_title="Real-Time Sales Dashboard",
    layout="wide",
)

st.title("🚀 Real-Time E-Commerce Sales Dashboard")

# Placeholder for auto-refresh
placeholder = st.empty()

while True:
    df = get_data()
    
    with placeholder.container():
        if not df.empty:
            # Key Metrics (Latest Window)
            latest_window = df['window_start'].max()
            latest_data = df[df['window_start'] == latest_window]
            
            total_sales = latest_data['total_sales'].sum()
            total_txns = latest_data['transaction_count'].sum()
            
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric(label="Latest Window Start", value=str(latest_window))
            kpi2.metric(label="Total Sales (Latest Window)", value=f"${total_sales:,.2f}")
            kpi3.metric(label="Transactions (Latest Window)", value=total_txns)
            
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Sales by Category (Latest Window)")
                chart = alt.Chart(latest_data).mark_bar().encode(
                    x='category',
                    y='total_sales',
                    color='category',
                    tooltip=['category', 'total_sales', 'transaction_count']
                ).interactive()
                st.altair_chart(chart, use_container_width=True)
                
            with col2:
                st.subheader("Sales Trend (Last 100 Windows)")
                # Aggregate by window for the trend line
                trend_df = df.groupby('window_start')['total_sales'].sum().reset_index()
                line_chart = alt.Chart(trend_df).mark_line(point=True).encode(
                    x='window_start',
                    y='total_sales',
                    tooltip=['window_start', 'total_sales']
                ).interactive()
                st.altair_chart(line_chart, use_container_width=True)
                
            st.markdown("### Raw Data")
            st.dataframe(df)
        else:
            st.warning("No data available yet. Waiting for pipeline to process data...")
            st.info("Ensure the Docker containers are running, the Producer is active, and Spark is processing.")
            
    time.sleep(2)
