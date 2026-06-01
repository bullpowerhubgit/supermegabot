import { Routes, Route } from 'react-router-dom';
import Navigation from './Komponenten/Navigation';
import Dashboard from './Komponenten/Dashboard';
import Produkte from './Komponenten/Produkte';
import Bestellungen from './Komponenten/Bestellungen';
import Marketing from './Komponenten/Marketing';
import SEO from './Komponenten/SEO';

export default function App() {
  return (
    <>
      <Navigation />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/produkte" element={<Produkte />} />
        <Route path="/bestellungen" element={<Bestellungen />} />
        <Route path="/marketing" element={<Marketing />} />
        <Route path="/seo" element={<SEO />} />
      </Routes>
    </>
  );
}
