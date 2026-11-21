from pathlib import Path
from openpyxl import load_workbook

src = Path(r"C:\Users\1\Downloads\PLAN_DE_TRABAJO_SparkCut (2).xlsx")
out_dir = Path(__file__).parent
dst = out_dir / "PLAN_DE_TRABAJO_SparkCut_completado.xlsx"
wb = load_workbook(src)
ws = wb["Plan de Trabajo"]

paths = {
    11: "01_evaluadores/01_acta_nombre_propuesta_valor.md",
    12: "01_evaluadores/04_guia_marca.md",
    13: "01_evaluadores/02_descripcion_tecnica.md",
    14: "01_evaluadores/03_diagrama_c4_y_secuencia.md",
    15: "01_evaluadores/05_modelo_datos_y_convenciones.md",
    16: "README_PAQUETE.md + carpeta completa",
    18: "02_modelo/SparkCut_entrenamiento_RNN_v3 (1).ipynb",
    19: "02_modelo/ml_artifacts_v6/model_*.pt + metrics.json",
    20: "03_datos_y_validacion/manual_template.csv",
    21: "02_modelo/ml_artifacts_v6/config.json + ficha_modelo.md",
    22: "02_modelo/01_ficha_modelo.md + metrics.json",
    24: "04_codigo_django/Dockerfile + docker-compose.yml",
    25: "04_codigo_django/accounts/",
    26: "04_codigo_django/videos/",
    27: "04_codigo_django/pipeline/ + videos/tasks.py",
    28: "04_codigo_django/pipeline/",
    29: "04_codigo_django/clips/ + pipeline/",
    30: "07_demo_y_sustentacion/01_guion_demo.md",
    32: "04_codigo_django/scoring/",
    33: "04_codigo_django/templates/",
    34: "04_codigo_django/clips/static/clips/editor.js",
    35: "04_codigo_django/templates/model/info.html",
    36: "06_pruebas_y_documentacion/04_bitacora_pruebas.md",
    37: "07_demo_y_sustentacion/01_guion_demo.md",
    39: "04_codigo_django/Dockerfile",
    40: "05_despliegue_kubernetes/k8s_base/",
    41: "05_despliegue_kubernetes/03_guia_verificacion_cluster.md",
    42: "05_despliegue_kubernetes/04_reporte_carga_plantilla.md",
    43: "05_despliegue_kubernetes/05_checklist_capturas.md",
    45: "06_pruebas_y_documentacion/05_manual_usuario_y_deploy.md (flujo de exportación)",
    46: "06_pruebas_y_documentacion/05_manual_usuario_y_deploy.md (flujo de edición)",
    47: "07_demo_y_sustentacion/04_version_estable.md",
    49: "06_pruebas_y_documentacion/pytest.ini + conftest.py",
    50: "06_pruebas_y_documentacion/06_informe_tecnico.md + EVALUACION_MODELO.md",
    51: "06_pruebas_y_documentacion/05_manual_usuario_y_deploy.md",
    52: "07_demo_y_sustentacion/01_guion_demo.md + 02_plan_b_y_datos_demo.md",
    53: "07_demo_y_sustentacion/03_ensayo_cronometrado.md",
    54: "README_PAQUETE.md + carpeta completa",
}

for row, rel in paths.items():
    old = ws.cell(row=row, column=9).value or ""
    ws.cell(row=row, column=9).value = f"{old}\n\nPaquete local: {rel}"
    ws.cell(row=row, column=9).alignment = ws.cell(row=row, column=9).alignment.copy(wrap_text=True)

# Add a small, explicit note without changing the workbook's sheet structure.
ws["B57"] = "PAQUETE LOCAL PREPARADO"
ws["B58"] = "Los artefactos referenciados en la columna ARTEFACTOS se copiaron o generaron en la carpeta del paquete. Las plantillas pendientes deben completarse con evidencia real."
ws["B58"].alignment = ws["B58"].alignment.copy(wrap_text=True)
wb.save(dst)
print(dst)
