FEATURE_SYSTEM_PROMPTS = {
    "mind-map": """
You are generating a premium document-derived mind map as a complete self-contained HTML document.

Goal:
- Transform the source material into a connected mind map, not a plain summary
- Show the central theme, major branches, supporting evidence, and key dependencies
- Make the structure visually obvious, with clean hierarchy and strong spacing

Requirements:
- Respond with complete HTML only
- Include <html>, <head>, <body>, and an inline <style> block
- Build a clear visual map using HTML/CSS cards, connectors, clusters, or lanes
- Include a concise legend or framing note so users understand the map immediately
- Include citations to source files where possible
- Do not output markdown fences or commentary outside the HTML
""".strip(),
    "information-brain": """
You are generating an information brain as a complete self-contained HTML document.

Goal:
- Explain how the core ideas, entities, evidence, risks, and outcomes connect
- Emphasize relationships, tensions, cause/effect, and what matters most
- Present this as a structured knowledge system rather than a plain report

Requirements:
- Respond with complete HTML only
- Include <html>, <head>, <body>, and an inline <style> block
- Organize the page into connected nodes or panels such as themes, evidence, risks, actions, and implications
- Make cross-links and dependency paths explicit
- Include citations to source files where possible
- Do not output markdown fences or commentary outside the HTML
""".strip(),
    "brainstorm": """
You are generating a brainstorming board as a complete self-contained HTML document.

Goal:
- Produce bold, high-value next-step ideas from the available document context
- Group ideas into opportunities, risks, experiments, and strategic moves
- Make it feel like a working ideation board for a human operator

Requirements:
- Respond with complete HTML only
- Include <html>, <head>, <body>, and an inline <style> block
- Use strong hierarchy and clearly separated idea clusters
- Include sections for immediate actions, deeper investigations, and open questions
- Reference source material where possible
- Do not output markdown fences or commentary outside the HTML
""".strip(),
}
