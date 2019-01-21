Glossary
========

.. glossary::

    environmental variable
    environmental variables
        In a shell, like Bash, an *environmental variable* is a variable that is inherited by child processes.

        When you open a new terminal window, you create a new shell. Each shell has its own set of variables, so if
        you did ``myvar=1`` in window A, then ``echo $myvar`` in window B won't print ``1`` because, in its list of
        variables, ``myvar`` isn't defined. Further, when you run a script, it gets its own shell. For example, make
        the following script, let's call it :file:`example.sh`::

            #!/bin/bash
            echo "myvar is $myvar"

        Make it executable (``chmod u+x example.sh``) and assign ``myvar='Hello world!'``. Now run :file:`example.sh`
        (``./example.sh``). It will print ``myvar is``, and *not* ``myvar is Hello world!`` because right now ``myvar``
        is a *local* variable - it exists in the shell for your terminal window, but *not* the shell started for
        :file:`example.sh`.

        However, if you make ``myvar`` an environmental variable by exporting it with ``export myvar``, then
        ``./example.sh`` *will* print ``myvar is Hello world!`` because environmental variables are inherited by child
        shells, we made ``myvar`` an environmental variable by exporting it, and the shell for :file:`example.sh` is
        a child of the terminal shell that started it.

        .. note::

            You can export and assign a value to a variable all at once: ``export myvar='Hello world!'``.