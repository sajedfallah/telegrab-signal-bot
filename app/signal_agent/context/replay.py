class ContextReplay:
    def __init__(self,engine):self.engine=engine
    def run(self,symbol,candles_by_tf,events,as_of):
        return self.engine.build(symbol,candles_by_tf,events,as_of=as_of)
