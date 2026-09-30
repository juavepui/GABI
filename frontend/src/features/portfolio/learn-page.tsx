import { Link } from 'react-router-dom';

const topics = [
  {
    title: 'Qué significa el score',
    text: 'El Composite Score combina bloques de valor, calidad, momentum y riesgo. Una puntuación alta no garantiza una rentabilidad futura; comprueba cobertura, fecha y procedencia de cada dato.',
    path: '/mercado',
    action: 'Examinar el ranking',
  },
  {
    title: 'Cómo se construye la cartera',
    text: 'La hipótesis congelada usa las 20 candidatas elegibles con más score y el mismo peso para cada una. Si hay menos de 20, se reparte entre las disponibles. La pantalla de Cartera usa esa regla compartida con Streamlit.',
    path: '/cartera',
    action: 'Ver cartera objetivo',
  },
  {
    title: 'Qué dicen las pruebas',
    text: 'Las pruebas retrospectivas y el seguimiento en vivo tienen límites distintos. GABI todavía no ha demostrado de forma independiente una ventaja clara frente al S&P 500. Cambiar el número de posiciones es un experimento, no un modelo validado.',
    path: '/investigacion',
    action: 'Ver Investigación',
  },
  {
    title: 'De una cifra a una tesis',
    text: 'Antes de operar, escribe qué tendría que pasar para que una empresa merezca su precio, qué invalidaría tu idea y cuándo la revisarás. El diario conserva esas notas en la base local.',
    path: '/cartera/diario',
    action: 'Abrir diario',
  },
];

export function LearnPage() {
  return (
    <div className="space-y-6">
      <header>
        <Link className="text-sm text-primary" to="/cartera">
          ← Cartera
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Aprender a usar GABI</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Guía breve de los conceptos que aparecen en las pantallas. Las definiciones de métricas y
          sus unidades están junto a cada dato de Mercado.
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        {topics.map((topic) => (
          <section key={topic.title} className="rounded-xl border bg-card p-6">
            <h2 className="text-lg font-semibold">{topic.title}</h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{topic.text}</p>
            <Link
              className="mt-5 inline-block text-sm font-medium text-primary underline"
              to={topic.path}
            >
              {topic.action} →
            </Link>
          </section>
        ))}
      </div>
    </div>
  );
}
