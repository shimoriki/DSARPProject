package com.example.alpha;

import com.example.beta.Beta;

public class Alpha {
    private Beta beta;
    public void doAlpha() { beta.doBeta(); }
    public String name() { return "alpha"; }
}
