import os
import pandas as pd
from supabase import create_client
import streamlit as st
import altair as alt

@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = (
        st.secrets.get("SUPABASE_SECRET_KEY")
        or st.secrets.get("SUPABASE_PUB_KEY")
    )
    return create_client(url, key)

supabase = init_supabase()

st.set_page_config(page_title="K-DIN 월별 리포트 대시보드", layout="wide")
st.title("K-DIN 월별 리포트 대시보드")
st.divider()

top_n = st.slider("그래프: 상위 N개 조직(총 리포트 수 기준)", 5, 50, 25, step=5)

st.subheader("통계 필터")

type_option = st.selectbox(
    "조직 유형(og.type) 필터",
    options=["모두", "PaAN", "PaAN 이외"],
    index=0,
    help="‘모두’, ‘PaAN’, 또는 ‘PaAN이 아닌 나머지(=PaAN 이외)’로 필터링합니다."
)

if type_option == "모두":
    where_clause = ""
elif type_option == "PaAN":
    where_clause = "WHERE og.type = 'PaAN'"
else:
    where_clause = "WHERE (og.type IS DISTINCT FROM 'PaAN')"

@st.cache_data(show_spinner=True, ttl=300)
def fetch_data(type_option: str, months: list[str] | None, orgs: list[str] | None):    
    payload = {
        "p_type": {"모두": None, "PaAN": "PaAN", "PaAN 이외": "NOT_PaAN"}[type_option],
        "p_months": months or None,
        "p_orgs": orgs or None,
    }
    res = supabase.rpc("rpc_monthly_org_reports", payload).execute()
    df = pd.DataFrame(res.data or [])
    if not df.empty:
        df = df.sort_values(["month", "orgGroupName"]).reset_index(drop=True)
    return df

df = fetch_data(type_option, None, None)

if df.empty:
    st.info("조회 결과가 없습니다. 조건을 바꿔보세요.")
    st.stop()

all_months = sorted(df["month"].unique().tolist())
all_orgs = df["orgGroupName"].unique().tolist()

col_m1, col_m2 = st.columns([2, 3])
with col_m1:
    st.markdown("**월(month) 필터**")
    selected_months = st.multiselect(
        "월을 선택하세요",
        options=all_months,
        default=all_months,
        key="month_filter",
        placeholder="월 선택"
    )
with col_m2:
    st.markdown("**조직(OrgGroupName) 필터**")
    selected_orgs = st.multiselect(
        "조직을 선택하세요",
        options=all_orgs,
        default=all_orgs,
        key="org_filter",
        placeholder="조직 선택"
    )
st.divider()
st.subheader("월별 통계 테이블")
filtered = df.copy()
if selected_months:
    filtered = filtered[filtered["month"].isin(selected_months)]
if selected_orgs:
    filtered = filtered[filtered["orgGroupName"].isin(selected_orgs)]

display_cols = ["month", "orgGroupName", "orgType", "unique_users", "session_count", "report_count"]
if filtered.empty:
    st.warning("필터 결과가 없습니다. 월 또는 조직 선택을 조정해 주세요.")
else:
    st.dataframe(filtered[display_cols], use_container_width=True)

st.divider()

st.subheader("조직별 총 리포트 수 (표 + 세로막대 그래프)")

if filtered.empty:
    st.info("집계할 데이터가 없습니다.")
else:
    totals = (
        filtered.groupby(["orgGroupId", "orgGroupName", "orgType"], as_index=False)
        .agg(total_sessions=("session_count", "sum"),
             total_reports=("report_count", "sum"))
        .sort_values("total_reports", ascending=False)
        .reset_index(drop=True)
    )

    st.markdown("**조직별 리포트/세션 총합**")
    st.dataframe(totals, use_container_width=True)

    plot_df = totals.head(top_n).copy().assign(label=lambda x: x["orgGroupName"])

    org_order = plot_df.sort_values("total_reports", ascending=False)["label"].tolist()

    plot_long = plot_df.melt(
        id_vars=["label"],
        value_vars=["total_reports", "total_sessions"],
        var_name="metric",
        value_name="value"
    )

    metric_name_map = {
        "total_reports": "Reports",
        "total_sessions": "Sessions"
    }
    plot_long["metric_label"] = plot_long["metric"].map(metric_name_map)

    st.markdown(f"**그룹 막대 그래프 (상위 {top_n}개 조직 · Reports & Sessions)**")

    chart = (
        alt.Chart(plot_long)
        .mark_bar()
        .encode(
            x=alt.X("label:N", sort=org_order, title="조직"),
            y=alt.Y("value:Q", title="개수"),
            color=alt.Color("metric_label:N", title=None),
            xOffset="metric_label:N",
            tooltip=[
                alt.Tooltip("label:N", title="조직"),
                alt.Tooltip("metric_label:N", title="지표"),
                alt.Tooltip("value:Q", title="값", format=",")
            ]
        )
        .properties(height=380)
    )

    st.altair_chart(chart, use_container_width=True)

with st.expander("현재 필터/쿼리 확인"):
    st.code(f"선택된 og.type 필터: {type_option}")
    st.code(f"선택된 월: {selected_months if df is not None else []}")
    st.code(f"선택된 조직: {selected_orgs if df is not None else []}")    
