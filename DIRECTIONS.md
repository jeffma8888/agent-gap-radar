# Foundry directions

foundry directions -- agent-gap-radar
  iter-03
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- retire `tools/check_locators.py`: one out-of-band network checker, not two
    - Candidate A2 -- one confidence-floor default, not three spellings (and delete cli.py's two dead imports)
    - Candidate A3 -- one register fixture builder, not four; delete the pair whose bodies match
    - Candidate B1 -- scan globs 181,440 paths to read 222: drive the walk from the tracked set
    - Candidate B2 -- the same glob is re-walked 32 times in one scan; memoise per scan
    - Candidate B3 -- MAX_SCAN_FILES documents a bound the code does not enforce
    winner: B1
    ship: pending (not yet decided)
  iter-02
    lenses: integration-and-adoption (iteration 02), simplification-and-deletion
    - Candidate A1 -- `radar scan --prd` hands a build loop a below-floor gap that `radar prd` refuses
    - Candidate A2 -- an empty or misdirected register reports health: `validate` prints OK on zero records
    - Candidate A3 -- `radar list --layer L`, the one flag the in-flight consumer contract names and the CLI does not have
    - Candidate B1 -- delete the code an AST census proves nothing calls
    - Candidate B2 -- one markdown document contract, not two, and the duplicate is the untested one
    - Candidate B3 -- one two-sided fixture proof, not two gates and three tree-builders
    winner: A1
    ship: PUSHED 4b7bba7
  iter-01
    lenses: hardening/DX -- iteration 01, integration-and-adoption (iteration 01)
    - Candidate A -- "Strongest source" is computed alphabetically, not from the evidence ladder
    - Candidate B -- the two-sided fixture proof exists three times and is reachable from none of them
    - Candidate C -- pin the renderer contract against a frozen fixture register (roadmap #8)
    - Candidate B1 -- `radar list` drops below-floor records and is missing both flags its own consumer contract publishes
    - Candidate B2 -- `radar scan` hands a CI gate no exit-code signal, so the only universal integration surface carries nothing
    - Candidate B3 -- scan output embeds an absolute machine path, so the artifact a consumer commits is not portable
    winner: B1
    ship: PUSHED c143c3b
3 scouted iterations
