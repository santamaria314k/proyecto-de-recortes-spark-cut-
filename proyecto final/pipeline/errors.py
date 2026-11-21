"""Errores legibles del pipeline de procesamiento.

Los mensajes de `PipelineError` son los que se muestran en `Video.error`; las
excepciones técnicas se registran en el log del worker.
"""


class PipelineError(Exception):
    """Error del pipeline cuyo mensaje puede mostrarse al usuario."""


class DependencyMissingError(PipelineError):
    """Falta una dependencia externa (paquete de Python o binario del sistema)."""
