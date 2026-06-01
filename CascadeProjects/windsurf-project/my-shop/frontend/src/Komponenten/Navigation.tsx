import { NavLink } from 'react-router-dom';

export default function Navigation() {
  const links = [
    { to: '/', label: 'Dashboard' },
    { to: '/produkte', label: 'Produkte' },
    { to: '/bestellungen', label: 'Bestellungen' },
    { to: '/marketing', label: 'Marketing' },
    { to: '/seo', label: 'SEO' },
  ];

  return (
    <nav>
      <ul>
        {links.map(link => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              className={({ isActive }) => isActive ? 'active' : ''}
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
