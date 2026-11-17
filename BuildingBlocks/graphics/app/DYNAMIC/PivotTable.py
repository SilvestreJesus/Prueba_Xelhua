import pandas as pd
from shared_components import Sys
from pivottablejs import pivot_ui

INPUTFILE = sys.argv[1]
OUTPUTFILE = sys.argv[2]

df = pd.read_csv(INPUTFILE)
pivot_ui(df,outfile_path='%sDynamicTable.html' % (OUTPUTFILE))

