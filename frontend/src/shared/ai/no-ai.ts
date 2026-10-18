export interface ExplanationService {
  explain(productId: number, cartProductIds: number[]): Promise<string>
}

/**
 * Interfaz futura. El backend actual no expone un endpoint de explicación
 * con IA, por lo que NO se implementa ExplanationService en esta versión.
 * Cualquier integración futura debe agregarse primero al backend Python.
 */
export const NO_AI_NOTE =
  "IA no integrada en el backend actual — NEXTCART funciona con el modelo local sin LLM"
