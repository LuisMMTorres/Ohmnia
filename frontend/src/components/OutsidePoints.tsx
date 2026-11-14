/** Datasheet points that fall outside the plotted range of the model curves. */
export function OutsidePoints({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="small muted">
      Pontos do datasheet fora da escala das curvas (amplie a faixa do gráfico ou ajuste o modelo
      para vê-los):
      <ul>
        {items.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}
