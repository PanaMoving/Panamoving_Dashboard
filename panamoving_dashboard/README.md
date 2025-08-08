# Panamoving Dashboard (Streamlit)

Dashboard interactivo para **Panamoving**:
- KPIs (Ingresos, CxC, CxP, Profit AB y Recalculado)
- Filtros por cliente, proveedor, tipo de proveedor y vencidos
- Gráficos (facturado vs cobrado, profit mensual, top clientes, crecimiento de clientes)
- Exportación a **Excel** y **PDF**

## Ejecutar en local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Desplegar gratis
1. Subí esta carpeta a un repo de **GitHub** (por ejemplo: `panamoving-dashboard`).
2. Andá a **share.streamlit.io** (Streamlit Community Cloud), conectá tu GitHub y elegí el repo.
3. Archivo principal: `app.py` — Python 3.10+.
4. Listo. Vas a poder compartir una URL pública.

## Datos
- Cargar el Excel manualmente (uploader) o pegar el link público de OneDrive/SharePoint.
- Hoja por defecto **Facturacion** (editable en la barra lateral).