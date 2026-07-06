import { useState } from 'react';
import { Entry } from './components/Entry';
import { Nav } from './components/Nav';
import { Hero } from './sections/Hero';
import { Problem } from './sections/Problem';
import { Vision } from './sections/Vision';
import { Pipeline } from './sections/Pipeline';
import { AttackViz } from './sections/AttackViz';
import { Benchmark } from './sections/Benchmark';
import { BuiltFor } from './sections/BuiltFor';
import { Local } from './sections/Local';
import { Download } from './sections/Download';
import { Future } from './sections/Future';

export default function App() {
  const [entered, setEntered] = useState(false);

  return (
    <div className="grain relative min-h-screen bg-ink">
      {!entered && <Entry onDone={() => setEntered(true)} />}
      <Nav visible={entered} />
      <main>
        <Hero started={entered} />
        <Problem />
        <Vision />
        <Pipeline />
        <AttackViz />
        <Benchmark />
        <BuiltFor />
        <Local />
        <Download />
        <Future />
      </main>
    </div>
  );
}
