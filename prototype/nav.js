function renderBottomNav(activeKey) {
  const items = [
    { key: 'chat', label: 'Chat', href: 'chat.html', icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M4 5h16v10H8l-4 4V5z" stroke-width="1.7" stroke-linejoin="round"/></svg>' },
    { key: 'dashboard', label: 'Dashboard', href: 'dashboard.html', icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="4" y="12" width="4" height="7" rx="1" stroke-width="1.7"/><rect x="10" y="8" width="4" height="11" rx="1" stroke-width="1.7"/><rect x="16" y="4" width="4" height="15" rx="1" stroke-width="1.7"/></svg>' },
    { key: 'activities', label: 'Activities', href: 'activities.html', icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M13 2 3 14h7l-1 8 11-14h-7l1-6z" stroke-width="1.7" stroke-linejoin="round"/></svg>' }
  ];
  const html = items.map(function (item) {
    const cls = item.key === activeKey ? 'active' : '';
    return '<a class="' + cls + '" href="' + item.href + '">' + item.icon + item.label + '</a>';
  }).join('');
  return '<div class="bottom-nav">' + html + '</div>';
}
